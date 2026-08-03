# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class AwsS3AttachmentRule(models.Model):
    _name = 'aws.s3.attachment.rule'
    _description = 'AWS S3 Attachment Sync Rule'
    _order = 'id desc'

    name = fields.Char(string='Name', compute='_compute_name', store=True)
    model_id = fields.Many2one('ir.model', string='Model', required=True, index=True, ondelete='cascade', domain=[('transient', '=', False)], help="Select Odoo model to sync attachments.")
    storage_mode = fields.Selection([
        ('s3_only', 'AWS S3 Only (Delete/Avoid local filestore)'),
        ('dual', 'Dual Storage (Store in Odoo and AWS S3)'),
        ('odoo_only', 'Odoo Only (Standard Odoo storage)')
    ], string='Storage Mode', required=True, default='s3_only', help="Choose how files will be saved.")
    root_folder = fields.Char(string='Root Folder', required=True, default='Sync/', help="S3 folder prefix (e.g. Sales/, Invoices/).")
    bucket_id = fields.Many2one('aws.s3.bucket', string='AWS S3 Bucket', required=True, domain=[('is_active', '=', True)])
    is_active = fields.Boolean(string='Active', default=True)

    _sql_constraints = [
        ('unique_model', 'unique(model_id)', 'A sync rule already exists for this model. Modify the existing one.')
    ]

    @api.depends('model_id')
    def _compute_name(self):
        for rule in self:
            if rule.model_id:
                rule.name = f"{rule.model_id.name} Sync Rule"
            else:
                rule.name = "New Sync Rule"


    @api.constrains('root_folder')
    def _check_root_folder(self):
        for rule in self:
            if not rule.root_folder:
                raise ValidationError(_("Root folder path cannot be empty."))

    def action_migrate_to_s3(self):
        self.ensure_one()
        if not self.bucket_id.is_active:
            raise UserError(_("AWS S3 Bucket is inactive."))
        if self.bucket_id.state != 'connected':
            # Run test connection
            self.bucket_id.action_test_connection()

        # Find attachments of this model that are not stored on S3 yet
        attachments = self.env['ir.attachment'].search([
            ('res_model', '=', self.model_id.model),
            ('is_s3_stored', '=', False),
            ('type', '=', 'binary')
        ])

        if not attachments:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Migration Info'),
                    'message': _('No outstanding attachments found to migrate for model %s.') % self.model_id.name,
                    'type': 'warning',
                    'sticky': False,
                }
            }

        success_count = 0
        failed_count = 0

        for attach in attachments:
            try:
                # Get the binary data
                data = attach.raw
                if not data:
                    continue

                # Generate the key
                s3_key = attach._get_s3_path(rule=self)
                if not s3_key:
                    continue

                # Upload to S3
                client = self.bucket_id._get_s3_client(self.bucket_id)
                mimetype = attach.mimetype or 'application/octet-stream'
                client.put_object(
                    Bucket=self.bucket_id.name,
                    Key=s3_key,
                    Body=data,
                    ContentType=mimetype
                )

                old_store_fname = attach.store_fname
                
                # Update attachment properties
                if self.storage_mode == 's3_only':
                    attach.sudo().write({
                        'store_fname': f"s3://{self.bucket_id.id}/{s3_key}",
                        'db_datas': False,
                        'is_s3_stored': True,
                        's3_bucket_id': self.bucket_id.id,
                        's3_key': s3_key,
                    })
                    # Clean up local filestore file
                    if old_store_fname:
                        attach._file_delete(old_store_fname)
                else:  # dual storage
                    attach.sudo().write({
                        'is_s3_stored': True,
                        's3_bucket_id': self.bucket_id.id,
                        's3_key': s3_key,
                    })

                # Create Log
                self.env['aws.s3.log'].sudo().create({
                    'name': 'Migration Upload',
                    'attachment_name': attach.name,
                    'res_model': attach.res_model,
                    'res_id': attach.res_id,
                    's3_key': s3_key,
                    'status': 'success',
                    'message': f"Migrated to S3 successfully."
                })
                success_count += 1
            except Exception as e:
                failed_count += 1
                self.env['aws.s3.log'].sudo().create({
                    'name': 'Migration Upload',
                    'attachment_name': attach.name,
                    'res_model': attach.res_model,
                    'res_id': attach.res_id,
                    's3_key': 'N/A',
                    'status': 'failed',
                    'message': f"Migration failed: {str(e)}"
                })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Migration Complete'),
                'message': _('Successfully migrated %d attachments. Failed: %d.') % (success_count, failed_count),
                'type': 'success' if failed_count == 0 else 'warning',
                'sticky': True,
            }
        }
