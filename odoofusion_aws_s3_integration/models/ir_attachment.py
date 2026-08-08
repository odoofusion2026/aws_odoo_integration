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
    def _file_write(self, bin_value, checksum):
        client, config = self._get_global_s3_client()

        if not client:
            return super()._file_write(bin_value, checksum)

        if config.routing_mode == 'rule_based':
            res_model = self.env.context.get('s3_log_model', '')
            rule = self._get_rule_for_model(res_model)

            if not rule or rule.storage_mode == 'odoo_only':
                return super()._file_write(bin_value, checksum)

        s3_key = f"{checksum[:2]}/{checksum}"

        try:
            try:
                client.head_object(Bucket=config.bucket_name, Key=s3_key)
                _logger.debug('S3 dedup hit: %s already exists in S3.', s3_key)
                return f's3://{s3_key}'
            except client.exceptions.ClientError as head_err:
                error_code = head_err.response['Error']['Code']
                if error_code != '404':
                    raise

            from odoo.tools.mimetypes import guess_mimetype
            mimetype = guess_mimetype(bin_value[:1024], default='application/octet-stream')

            file_size = len(bin_value)
            if file_size > 100 * 1024 * 1024:
                self._s3_multipart_upload(client, config, s3_key, bin_value, mimetype)
            else:
                client.put_object(
                    Bucket=config.bucket_name,
                    Key=s3_key,
                    Body=bin_value,
                    ContentType=mimetype,
                )

            _logger.debug('S3 upload: %s (%d bytes)', s3_key, file_size)

            self.env['aws.s3.log'].sudo().create({
                'name': 'Upload',
                'attachment_name': s3_key.split('/')[-1],
                'res_model': self.env.context.get('s3_log_model', ''),
                'res_id': self.env.context.get('s3_log_res_id', 0),
                's3_key': s3_key,
                'status': 'success',
                'message': f"Uploaded {file_size} bytes to s3://{config.bucket_name}/{s3_key}",
            })

            return f's3://{s3_key}'

        except Exception as e:
            _logger.error('S3 _file_write failed for key %s: %s — falling back to local filestore.', s3_key, e)
            self.env['aws.s3.log'].sudo().create({
                'name': 'Upload',
                'attachment_name': s3_key.split('/')[-1] if 's3_key' in locals() else 'unknown',
                's3_key': s3_key if 's3_key' in locals() else 'unknown',
                'status': 'failed',
                'message': f'Upload failed: {e} — fell back to local filestore.',
            })
            return super()._file_write(bin_value, checksum)

    @api.model
    def _file_read(self, fname):
        if not (fname and fname.startswith('s3://')):
            return super()._file_read(fname)

        s3_key = fname[5:]
        client, config = self._get_global_s3_client()

        if not client:
            _logger.error('S3 _file_read: no active S3 config for key %s', s3_key)
            return b''

        try:
            response = client.get_object(Bucket=config.bucket_name, Key=s3_key)
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

        s3_key = fname[5:]
        try:
            self.env['aws.s3.delete.queue'].sudo().create({'s3_key': s3_key})
            _logger.debug('S3 delete queued for key: %s', s3_key)
        except Exception as e:
            _logger.error('Failed to queue S3 deletion for %s: %s', s3_key, e)

    def _to_http_stream(self):
        self.ensure_one()

        if not (self.store_fname and self.store_fname.startswith('s3://')):
            return super()._to_http_stream()

        client, config = self._get_global_s3_client()
        if not client:
            return super()._to_http_stream()

        s3_key = self.store_fname[5:]

        try:
            if config.public_bucket:
                if config.cdn_url:
                    url = f"{config.cdn_url.rstrip('/')}/{s3_key}"
                else:
                    url = (
                        f"https://{config.bucket_name}"
                        f".s3.{config.region_name}.amazonaws.com/{s3_key}"
                    )
            else:
                url = self._get_cached_presigned_url(
                    client, config, s3_key,
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
    def _get_cached_presigned_url(self, client, config, s3_key, mimetype=None):
        now = datetime.utcnow()
        cached = _presigned_url_cache.get(s3_key)

        if cached and cached[1] > now:
            return cached[0]

        params = {'Bucket': config.bucket_name, 'Key': s3_key}
        if mimetype:
            params['ResponseContentType'] = mimetype

        url = client.generate_presigned_url(
            'get_object',
            Params=params,
            ExpiresIn=config.presigned_ttl or 3600,
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
    def _s3_multipart_upload(self, client, config, s3_key, bin_value, mimetype):
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
            config.bucket_name,
            s3_key,
            ExtraArgs={'ContentType': mimetype},
            Config=transfer_config,
        )

    @api.model_create_multi
    def create(self, vals_list):
        first_with_model = next(
            (v for v in vals_list if v.get('res_model')),
            vals_list[0] if vals_list else {}
        )
        ctx = dict(
            self.env.context,
            s3_log_model=first_with_model.get('res_model', ''),
            s3_log_res_id=first_with_model.get('res_id') or 0,
        )
        return super(IrAttachment, self.with_context(ctx)).create(vals_list)

    def write(self, vals):
        if 'datas' not in vals and 'raw' not in vals:
            return super().write(vals)

        for record in self:
            res_model = vals.get('res_model', record.res_model) or ''
            res_id = vals.get('res_id', record.res_id) or 0

            ctx = dict(
                self.env.context,
                s3_log_model=res_model,
                s3_log_res_id=res_id,
            )

            old_fname = record.store_fname
            super(IrAttachment, record.with_context(ctx)).write(vals)

            if old_fname and old_fname.startswith('s3://'):
                if record.store_fname != old_fname:
                    self._file_delete(old_fname)

        return True

    def _mark_for_gc(self, fname):
        if fname and fname.startswith('s3://'):
            s3_key = fname[5:]
            try:
                self.env['aws.s3.delete.queue'].sudo().create({'s3_key': s3_key})
            except Exception as e:
                _logger.error('Failed to queue S3 GC for %s: %s', s3_key, e)
            return
        return super()._mark_for_gc(fname)
