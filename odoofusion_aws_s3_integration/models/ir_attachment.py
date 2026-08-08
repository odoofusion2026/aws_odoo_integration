# -*- coding: utf-8 -*-
# Author: Metamorphosis, Joyanto
"""
ir_attachment.py — Universal AWS S3 Storage Engine Override (Odoo 19)
"""

import logging
import threading
from datetime import datetime, timedelta

from odoo import models, fields, api, tools, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

_s3_thread_local = threading.local()
_presigned_url_cache: dict = {}
_PRESIGNED_CACHE_TTL_MINUTES = 55


class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    is_s3_stored = fields.Boolean(string='Stored on S3', default=False, index=True)
    s3_key = fields.Char(string='S3 Object Key', index=True)
    s3_bucket_id = fields.Many2one('aws.s3.bucket', string='AWS S3 Bucket', index=True, ondelete='set null')

    @api.model
    @tools.ormcache()
    def _get_active_s3_config(self):
        return self.env['aws.s3.config'].sudo().search(
            [('is_active', '=', True)], limit=1
        )

    @api.model
    @tools.ormcache('res_model')
    def _get_rule_for_model(self, res_model):
        if not res_model:
            return self.env['aws.s3.attachment.rule'].browse()
        return self.env['aws.s3.attachment.rule'].sudo().search(
            [('model_id.model', '=', res_model), ('is_active', '=', True)],
            limit=1,
        )

    @api.model
    def _get_global_s3_client(self):
        config = self._get_active_s3_config()
        if not config:
            return None, None

        cache_key = f"{config.aws_access_key}:{config.region_name}:{config.bucket_name}"
        pool = getattr(_s3_thread_local, 'clients', {})
        if cache_key not in pool:
            client = config._build_s3_client()
            pool[cache_key] = client
            _s3_thread_local.clients = pool
            _logger.debug('S3 client pool: created new client for %s', config.bucket_name)

        return pool[cache_key], config

    @api.model
    def _compute_s3_key_static(self, res_model, res_id, name, rule):
        """Generate a 3-tier S3 object key path for a given record."""
        root_folder = (rule.root_folder or '').strip('/')
        if root_folder:
            root_folder += '/'

        record = None
        if res_model and res_id:
            try:
                record = self.env[res_model].browse(res_id).exists()
            except Exception:
                record = None

        path_parts = []
        if record:
            if res_model == 'crm.lead':
                path_parts = [record.name or '']
            elif res_model == 'sale.order':
                path_parts = [getattr(record.partner_id, 'name', 'General') or 'General', record.name or '']
            elif res_model == 'account.move':
                path_parts = [getattr(record.partner_id, 'name', 'General') or 'General', record.name or '']
            elif res_model == 'purchase.order':
                path_parts = [getattr(record.partner_id, 'name', 'General') or 'General', record.name or '']
            elif res_model == 'hr.employee':
                path_parts = [record.name or '']
            elif res_model == 'project.task':
                path_parts = [getattr(record.project_id, 'name', 'General') or 'General', record.name or '']
            elif res_model == 'helpdesk.ticket':
                path_parts = [record.name or '']
            elif res_model == 'stock.picking':
                path_parts = [record.name or '']
            else:
                path_parts = [record.display_name or str(record.id)]
        else:
            path_parts = ['Unsorted']

        clean_parts = [str(p).replace('/', '_').strip() for p in path_parts if p]
        sub_path = '/'.join(clean_parts)
        if sub_path:
            sub_path += '/'

        filename = (name or 'attachment').replace('/', '_')
        return f"{root_folder}{sub_path}{filename}"

    def _get_s3_path(self, rule=None):
        """Return the S3 key path for this attachment."""
        self.ensure_one()
        if not rule:
            rule = self.env['aws.s3.attachment.rule'].sudo().search([
                ('model_id.model', '=', self.res_model),
                ('is_active', '=', True),
            ], limit=1)
        if not rule:
            return False
        return self._compute_s3_key_static(self.res_model, self.res_id, self.name, rule)

    @api.model
    def _get_active_s3_rule(self, res_model):
        """Fetch the active S3 attachment rule for a given model."""
        if not res_model:
            return False
        return self.env['aws.s3.attachment.rule'].sudo().search([
            ('model_id.model', '=', res_model),
            ('is_active', '=', True),
            ('storage_mode', '!=', 'odoo_only'),
        ], limit=1)

    @api.model
    def _parse_s3_fname(self, fname):
        """Parse s3://<bucket_id>/<key> or s3://<key> and return (client, bucket_name, key)."""
        if not (fname and fname.startswith('s3://')):
            return None, None, None

        s3_key = fname[5:]
        bucket_id = None
        parts = s3_key.split('/', 1)
        if len(parts) == 2 and parts[0].isdigit():
            try:
                bucket_id = int(parts[0])
                s3_key = parts[1]
            except ValueError:
                pass

        if bucket_id:
            bucket = self.env['aws.s3.bucket'].sudo().browse(bucket_id)
            if bucket and bucket.exists():
                client = bucket._get_s3_client(bucket)
                return client, bucket.name, s3_key

        client, config = self._get_global_s3_client()
        if client and config:
            return client, config.bucket_name, s3_key

        return None, None, None

    # ----------------------------------------------------------
    # Core S3 Storage Hook — _get_datas_related_values
    # ----------------------------------------------------------

    def _get_datas_related_values(self, data, mimetype):
        config = self._get_active_s3_config()
        if not config:
            return super()._get_datas_related_values(data, mimetype)

        s3_storage_mode = self.env.context.get('s3_storage_mode')
        s3_bucket_id = self.env.context.get('s3_bucket_id')
        s3_key = self.env.context.get('s3_key')

        if config.routing_mode == 'rule_based':
            if not s3_storage_mode or s3_storage_mode == 'odoo_only' or not s3_key or not s3_bucket_id:
                return super()._get_datas_related_values(data, mimetype)
        else:
            s3_storage_mode = 's3_only'
            checksum = self._compute_checksum(data)
            s3_key = f"{checksum[:2]}/{checksum}"
            s3_bucket_id = None

        if s3_bucket_id:
            bucket = self.env['aws.s3.bucket'].sudo().browse(s3_bucket_id)
            if bucket and bucket.exists():
                client = bucket._get_s3_client(bucket)
                bucket_name = bucket.name
            else:
                client, _ = self._get_global_s3_client()
                bucket_name = config.bucket_name
        else:
            client, _ = self._get_global_s3_client()
            bucket_name = config.bucket_name

        if not client:
            return super()._get_datas_related_values(data, mimetype)

        checksum = self._compute_checksum(data)

        try:
            index_content = self._index(data, mimetype, checksum=checksum)
        except TypeError:
            index_content = self._index(data, mimetype)

        try:
            try:
                client.head_object(Bucket=bucket_name, Key=s3_key)
                _logger.debug('S3 dedup hit: %s already exists in S3.', s3_key)
            except client.exceptions.ClientError as head_err:
                error_code = head_err.response['Error']['Code']
                if error_code != '404':
                    raise

                file_size = len(data)
                if file_size > 100 * 1024 * 1024:
                    self._s3_multipart_upload_custom(client, bucket_name, s3_key, data, mimetype)
                else:
                    client.put_object(
                        Bucket=bucket_name,
                        Key=s3_key,
                        Body=data,
                        ContentType=mimetype or 'application/octet-stream',
                    )

            self.env['aws.s3.log'].sudo().create({
                'name': 'Upload',
                'attachment_name': s3_key.split('/')[-1],
                'res_model': self.env.context.get('s3_log_model', ''),
                'res_id': self.env.context.get('s3_log_res_id', 0),
                's3_key': s3_key,
                'status': 'success',
                'message': f"Uploaded file to S3 bucket '{bucket_name}' key '{s3_key}'",
            })

        except Exception as e:
            _logger.error("AWS S3 Upload Failed for key %s: %s", s3_key, e)
            self.env['aws.s3.log'].sudo().create({
                'name': 'Upload',
                'attachment_name': s3_key.split('/')[-1] if s3_key else 'unknown',
                's3_key': s3_key or 'unknown',
                'status': 'failed',
                'message': f"Upload failed: {e}",
            })
            raise UserError(_("AWS S3 Upload Failed: %s") % str(e))

        values = {
            'file_size': len(data),
            'checksum': checksum,
            'index_content': index_content,
            'is_s3_stored': True,
            's3_bucket_id': s3_bucket_id or False,
            's3_key': s3_key,
        }

        bucket_prefix = f"{s3_bucket_id}/" if s3_bucket_id else ""
        if s3_storage_mode == 's3_only':
            values['store_fname'] = f"s3://{bucket_prefix}{s3_key}"
            values['db_datas'] = False
        else:
            if self._storage() != 'db':
                values['store_fname'] = self._file_write(data, checksum)
                values['db_datas'] = False
            else:
                values['store_fname'] = False
                values['db_datas'] = data
        return values

    # ----------------------------------------------------------
    # _file_read — intercept s3:// pointers and dual fallback
    # ----------------------------------------------------------

    @api.model
    def _file_read(self, fname):
        if not (fname and fname.startswith('s3://')):
            return super()._file_read(fname)

        client, bucket_name, s3_key = self._parse_s3_fname(fname)
        if not client:
            _logger.error('S3 _file_read: no active S3 client for %s', fname)
            return b''

        try:
            response = client.get_object(Bucket=bucket_name, Key=s3_key)
            return response['Body'].read()
        except Exception as e:
            _logger.error('S3 _file_read failed for %s: %s', s3_key, e)
            self.env['aws.s3.log'].sudo().create({
                'name': 'Read',
                'attachment_name': s3_key.split('/')[-1],
                's3_key': s3_key,
                'status': 'failed',
                'message': f'Read failed: {e}',
            })
            return b''

    @api.model
    def _file_delete(self, fname):
        if not (fname and fname.startswith('s3://')):
            return super()._file_delete(fname)

        client, bucket_name, s3_key = self._parse_s3_fname(fname)
        try:
            self.env['aws.s3.delete.queue'].sudo().create({
                's3_key': s3_key,
                'bucket_name': bucket_name,
            })
            _logger.debug('S3 delete queued for key: %s (bucket: %s)', s3_key, bucket_name)
        except Exception as e:
            _logger.error('Failed to queue S3 deletion for %s: %s', s3_key, e)

    def _to_http_stream(self):
        self.ensure_one()

        if not (self.store_fname and self.store_fname.startswith('s3://')):
            return super()._to_http_stream()

        config = self._get_active_s3_config()
        client, bucket_name, s3_key = self._parse_s3_fname(self.store_fname)

        if not client or not config:
            return super()._to_http_stream()

        try:
            if config.public_bucket:
                if config.cdn_url:
                    url = f"{config.cdn_url.rstrip('/')}/{s3_key}"
                else:
                    url = (
                        f"https://{bucket_name}"
                        f".s3.{config.region_name}.amazonaws.com/{s3_key}"
                    )
            else:
                url = self._get_cached_presigned_url(
                    client, bucket_name, s3_key,
                    ttl=config.presigned_ttl,
                    mimetype=self.mimetype or None,
                )

            from odoo.http import Stream
            return Stream(
                type='url',
                url=url,
                mimetype=self.mimetype or 'application/octet-stream',
                download_name=self.name,
                etag=self.checksum,
                public=self.public,
            )

        except Exception as e:
            _logger.error('S3 _to_http_stream failed for attachment %s (key=%s): %s', self.id, s3_key, e)
            return super()._to_http_stream()

    @api.model
    def _get_cached_presigned_url(self, client, bucket_name, s3_key, ttl, mimetype=None):
        now = datetime.utcnow()
        cached = _presigned_url_cache.get(s3_key)

        if cached and cached[1] > now:
            return cached[0]

        params = {'Bucket': bucket_name, 'Key': s3_key}
        if mimetype:
            params['ResponseContentType'] = mimetype

        url = client.generate_presigned_url(
            'get_object',
            Params=params,
            ExpiresIn=ttl or 3600,
        )

        expires_at = now + timedelta(minutes=_PRESIGNED_CACHE_TTL_MINUTES)
        _presigned_url_cache[s3_key] = (url, expires_at)

        if len(_presigned_url_cache) % 100 == 0:
            self._cleanup_presigned_cache()

        return url

    @api.model
    def _cleanup_presigned_cache(self):
        now = datetime.utcnow()
        expired = [k for k, (_, exp) in _presigned_url_cache.items() if exp <= now]
        for k in expired:
            _presigned_url_cache.pop(k, None)

    @api.model
    def _s3_multipart_upload_custom(self, client, bucket_name, s3_key, bin_value, mimetype):
        import io
        from boto3.s3.transfer import TransferConfig

        transfer_config = TransferConfig(
            multipart_threshold=100 * 1024 * 1024,
            max_concurrency=4,
            multipart_chunksize=20 * 1024 * 1024,
        )

        file_obj = io.BytesIO(bin_value)
        client.upload_fileobj(
            file_obj,
            bucket_name,
            s3_key,
            ExtraArgs={'ContentType': mimetype},
            Config=transfer_config,
        )

    @api.model_create_multi
    def create(self, vals_list):
        results = self.env['ir.attachment']
        config = self._get_active_s3_config()

        for vals in vals_list:
            res_model = vals.get('res_model', '')
            res_id = vals.get('res_id') or 0
            name = vals.get('name', 'attachment')

            rule = self._get_active_s3_rule(res_model) if config else False

            if rule and rule.bucket_id and rule.bucket_id.is_active:
                s3_key = self._compute_s3_key_static(res_model, res_id, name, rule)
                ctx = dict(
                    self.env.context,
                    s3_log_model=res_model,
                    s3_log_res_id=res_id,
                    s3_key=s3_key,
                    s3_bucket_id=rule.bucket_id.id,
                    s3_storage_mode=rule.storage_mode,
                )
                rec = super(IrAttachment, self.with_context(ctx)).create([vals])
            else:
                if config and config.routing_mode == 'global':
                    ctx = dict(
                        self.env.context,
                        s3_log_model=res_model,
                        s3_log_res_id=res_id,
                    )
                    rec = super(IrAttachment, self.with_context(ctx)).create([vals])
                else:
                    rec = super(IrAttachment, self).create([vals])

            results |= rec
        return results

    def write(self, vals):
        if 'datas' not in vals and 'raw' not in vals:
            return super().write(vals)

        config = self._get_active_s3_config()

        for record in self:
            res_model = vals.get('res_model', record.res_model) or ''
            res_id = vals.get('res_id', record.res_id) or 0
            name = vals.get('name', record.name) or 'attachment'

            rule = self._get_active_s3_rule(res_model) if config else False
            old_fname = record.store_fname

            if rule and rule.bucket_id and rule.bucket_id.is_active:
                s3_key = self._compute_s3_key_static(res_model, res_id, name, rule)
                ctx = dict(
                    self.env.context,
                    s3_log_model=res_model,
                    s3_log_res_id=res_id,
                    s3_key=s3_key,
                    s3_bucket_id=rule.bucket_id.id,
                    s3_storage_mode=rule.storage_mode,
                )
                super(IrAttachment, record.with_context(ctx)).write(vals)
            else:
                if config and config.routing_mode == 'global':
                    ctx = dict(
                        self.env.context,
                        s3_log_model=res_model,
                        s3_log_res_id=res_id,
                    )
                    super(IrAttachment, record.with_context(ctx)).write(vals)
                else:
                    super(IrAttachment, record).write(vals)

            if old_fname and old_fname.startswith('s3://'):
                if record.store_fname != old_fname:
                    self._file_delete(old_fname)

        return True

    def _mark_for_gc(self, fname):
        if fname and fname.startswith('s3://'):
            client, bucket_name, s3_key = self._parse_s3_fname(fname)
            try:
                self.env['aws.s3.delete.queue'].sudo().create({
                    's3_key': s3_key,
                    'bucket_name': bucket_name,
                })
            except Exception as e:
                _logger.error('Failed to queue S3 GC for %s: %s', s3_key, e)
            return
        return super()._mark_for_gc(fname)
