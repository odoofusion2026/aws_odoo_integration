# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    is_s3_stored = fields.Boolean(string='Stored on S3', default=False, index=True)
    s3_bucket_id = fields.Many2one('aws.s3.bucket', string='AWS S3 Bucket', index=True, ondelete='set null')
    s3_key = fields.Char(string='S3 Object Key', index=True)

    # ----------------------------------------------------------
    # S3 Path Generation Helpers
    # ----------------------------------------------------------

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

    # ----------------------------------------------------------
    # Core S3 Storage Hook — _get_datas_related_values
    # ----------------------------------------------------------

    def _get_datas_related_values(self, data, mimetype):
        s3_storage_mode = self.env.context.get('s3_storage_mode')
        s3_bucket_id = self.env.context.get('s3_bucket_id')
        s3_key = self.env.context.get('s3_key')

        if s3_storage_mode and s3_bucket_id and s3_key and s3_storage_mode != 'odoo_only':
            bucket = self.env['aws.s3.bucket'].sudo().browse(s3_bucket_id)
            checksum = self._compute_checksum(data)

            try:
                index_content = self._index(data, mimetype, checksum=checksum)
            except TypeError:
                index_content = self._index(data, mimetype)

            # Upload to AWS S3
            try:
                client = bucket._get_s3_client(bucket)
                client.put_object(
                    Bucket=bucket.name,
                    Key=s3_key,
                    Body=data,
                    ContentType=mimetype or 'application/octet-stream',
                )
                self.env['aws.s3.log'].sudo().create({
                    'name': 'Upload',
                    'attachment_name': s3_key.split('/')[-1],
                    'res_model': self.env.context.get('s3_res_model', ''),
                    'res_id': self.env.context.get('s3_res_id', 0),
                    's3_key': s3_key,
                    'status': 'success',
                    'message': f"Uploaded to S3 bucket '{bucket.name}' key '{s3_key}'",
                })
            except Exception as e:
                self.env['aws.s3.log'].sudo().create({
                    'name': 'Upload',
                    'attachment_name': s3_key.split('/')[-1],
                    'res_model': self.env.context.get('s3_res_model', ''),
                    'res_id': self.env.context.get('s3_res_id', 0),
                    's3_key': s3_key,
                    'status': 'failed',
                    'message': f"Upload failed: {e}",
                })
                raise UserError(_("AWS S3 Upload Failed: %s") % str(e))

            values = {
                'file_size': len(data),
                'checksum': checksum,
                'index_content': index_content,
                'is_s3_stored': True,
                's3_bucket_id': bucket.id,
                's3_key': s3_key,
            }

            if s3_storage_mode == 's3_only':
                # Store a lightweight s3:// pointer; no local file written
                values['store_fname'] = f"s3://{bucket.id}/{s3_key}"
                values['db_datas'] = False
            else:
                # dual: also write locally
                if self._storage() != 'db':
                    values['store_fname'] = self._file_write(data, checksum)
                    values['db_datas'] = False
                else:
                    values['store_fname'] = False
                    values['db_datas'] = data
            return values

        return super()._get_datas_related_values(data, mimetype)

    # ----------------------------------------------------------
    # _file_read — intercept s3:// pointers and dual fallback
    # ----------------------------------------------------------

    @api.model
    def _file_read(self, fname):
        """Read a file; if fname is an s3:// pointer, fetch from AWS S3."""
        if fname and fname.startswith('s3://'):
            try:
                # fname format: s3://<bucket_db_id>/<s3_key>
                rest = fname[5:]
                slash_pos = rest.index('/')
                bucket_id = int(rest[:slash_pos])
                s3_key = rest[slash_pos + 1:]

                bucket = self.env['aws.s3.bucket'].sudo().browse(bucket_id)
                client = bucket._get_s3_client(bucket)
                response = client.get_object(Bucket=bucket.name, Key=s3_key)
                return response['Body'].read()
            except Exception as e:
                _logger.error("S3 _file_read failed for %s: %s", fname, e)
                self.env['aws.s3.log'].sudo().create({
                    'name': 'Read',
                    'attachment_name': fname,
                    's3_key': fname,
                    'status': 'failed',
                    'message': f"Read failed from S3: {e}",
                })
                return b''

        # Standard local read; then try dual-storage S3 fallback if local missing
        local_data = super()._file_read(fname)
        if local_data:
            return local_data

        # Self-healing: if local file is gone but attachment is dual-stored on S3
        attach = self.sudo().search([
            ('store_fname', '=', fname),
            ('is_s3_stored', '=', True),
        ], limit=1)
        if attach and attach.s3_key and attach.s3_bucket_id:
            try:
                client = attach.s3_bucket_id._get_s3_client(attach.s3_bucket_id)
                response = client.get_object(
                    Bucket=attach.s3_bucket_id.name, Key=attach.s3_key
                )
                _logger.info("S3 self-healing fallback read: %s", attach.s3_key)
                return response['Body'].read()
            except Exception as e:
                _logger.error("S3 dual-storage fallback failed for %s: %s", fname, e)
                self.env['aws.s3.log'].sudo().create({
                    'name': 'Read (Fallback)',
                    'attachment_name': attach.name,
                    's3_key': attach.s3_key,
                    'status': 'failed',
                    'message': f"Dual fallback read failed: {e}",
                })

        return b''

    # ----------------------------------------------------------
    # create — inject S3 context per-record
    # ----------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        results = self.env['ir.attachment']
        for vals in vals_list:
            res_model = vals.get('res_model')
            rule = self._get_active_s3_rule(res_model)

            if rule and rule.bucket_id and rule.bucket_id.is_active:
                res_id = vals.get('res_id')
                name = vals.get('name')
                s3_key = self._compute_s3_key_static(res_model, res_id, name, rule)
                ctx = dict(
                    self.env.context,
                    s3_storage_mode=rule.storage_mode,
                    s3_bucket_id=rule.bucket_id.id,
                    s3_key=s3_key,
                    s3_res_model=res_model,
                    s3_res_id=res_id or 0,
                )
                rec = super(IrAttachment, self.with_context(ctx)).create([vals])
            else:
                rec = super(IrAttachment, self).create([vals])

            results |= rec
        return results

    # ----------------------------------------------------------
    # write — inject S3 context only when file data changes
    # ----------------------------------------------------------

    def write(self, vals):
        if not ('datas' in vals or 'raw' in vals):
            return super().write(vals)

        # Process each record individually to apply per-record S3 context
        for record in self:
            res_model = vals.get('res_model', record.res_model)
            res_id = vals.get('res_id', record.res_id)
            name = vals.get('name', record.name)

            rule = self._get_active_s3_rule(res_model)

            if rule and rule.bucket_id and rule.bucket_id.is_active:
                s3_key = self._compute_s3_key_static(res_model, res_id, name, rule)
                ctx = dict(
                    self.env.context,
                    s3_storage_mode=rule.storage_mode,
                    s3_bucket_id=rule.bucket_id.id,
                    s3_key=s3_key,
                    s3_res_model=res_model,
                    s3_res_id=res_id or 0,
                )
                old_store_fname = record.store_fname
                super(IrAttachment, record.with_context(ctx)).write(vals)
                # If S3 Only, also clean up old local filestore file
                if (rule.storage_mode == 's3_only'
                        and old_store_fname
                        and not old_store_fname.startswith('s3://')):
                    record._file_delete(old_store_fname)
            else:
                super(IrAttachment, record).write(vals)

        return True

    # ----------------------------------------------------------
    # unlink — delete from S3 after removing from Odoo
    # ----------------------------------------------------------

    def unlink(self):
        # Capture S3 references before deletion
        to_delete_s3 = [
            (att.s3_bucket_id, att.s3_key)
            for att in self
            if att.is_s3_stored and att.s3_key and att.s3_bucket_id
        ]

        res = super().unlink()

        for bucket, key in to_delete_s3:
            try:
                client = bucket._get_s3_client(bucket)
                client.delete_object(Bucket=bucket.name, Key=key)
                self.env['aws.s3.log'].sudo().create({
                    'name': 'Delete',
                    'attachment_name': key.split('/')[-1],
                    's3_key': key,
                    'status': 'success',
                    'message': f"Deleted from S3 bucket '{bucket.name}'",
                })
            except Exception as e:
                self.env['aws.s3.log'].sudo().create({
                    'name': 'Delete',
                    'attachment_name': key.split('/')[-1],
                    's3_key': key,
                    'status': 'failed',
                    'message': f"S3 delete failed: {e}",
                })
        return res
