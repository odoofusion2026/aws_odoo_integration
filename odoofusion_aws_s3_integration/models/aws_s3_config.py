# -*- coding: utf-8 -*-
# Author: Metamorphosis, Joyanto

import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class AwsS3Config(models.Model):
    _name = 'aws.s3.config'
    _description = 'AWS S3 Global Storage Configuration'
    _order = 'id desc'

    name = fields.Char(
        string='Configuration Name',
        required=True,
        default='Global S3 Storage',
    )
    bucket_name = fields.Char(
        string='S3 Bucket Name',
        required=True,
        help='Globally unique S3 bucket name. Must already exist in AWS.',
    )
    region_name = fields.Char(
        string='AWS Region',
        required=True,
        default='ap-southeast-1',
        help='AWS region where the bucket is hosted (e.g. us-east-1, ap-southeast-1).',
    )
    aws_access_key = fields.Char(
        string='Access Key ID',
        required=True,
    )
    aws_secret_key = fields.Char(
        string='Secret Access Key',
        required=True,
    )
    is_active = fields.Boolean(
        string='Active (Enable S3 Storage)',
        default=False,
        help='Master switch. When enabled, new attachments are routed to S3 according to the Routing Mode below.',
    )
    routing_mode = fields.Selection(
        selection=[
            ('global', 'Global — All Models (Upload Everything to S3)'),
            ('rule_based', 'Rule-Based — Selected Models Only'),
        ],
        string='Routing Mode',
        required=True,
        default='global',
        help='Global: every new attachment goes to S3.\n'
             'Rule-Based: only models that have an active Sync Rule with s3_only or dual are uploaded.',
    )
    public_bucket = fields.Boolean(
        string='Public Bucket',
        default=False,
        help='If checked, permanent public S3 URLs are used instead of expiring pre-signed URLs.',
    )
    cdn_url = fields.Char(
        string='CDN Base URL',
        help='Optional CloudFront or custom CDN domain to serve files.',
    )
    presigned_ttl = fields.Integer(
        string='Pre-signed URL TTL (seconds)',
        default=3600,
        help='How long pre-signed URLs remain valid for private buckets (min: 300).',
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Not Tested'),
            ('connected', 'Connected'),
            ('failed', 'Connection Failed'),
        ],
        string='Connection Status',
        default='draft',
        readonly=True,
    )

    total_files_synced = fields.Integer(
        string='Files in S3',
        compute='_compute_stats',
    )
    pending_deletes = fields.Integer(
        string='Pending Deletions',
        compute='_compute_stats',
    )

    def _compute_stats(self):
        for rec in self:
            rec.total_files_synced = self.env['ir.attachment'].sudo().search_count([
                ('store_fname', 'like', 's3://%'),
            ])
            rec.pending_deletes = self.env['aws.s3.delete.queue'].sudo().search_count([
                ('state', '=', 'pending'),
            ])

    @api.constrains('is_active')
    def _check_single_active(self):
        for rec in self:
            if rec.is_active:
                others = self.search([('is_active', '=', True), ('id', '!=', rec.id)])
                if others:
                    raise ValidationError(_(
                        'Only ONE S3 configuration can be active at a time.\n'
                        'Please deactivate "%s" first.'
                    ) % others[0].name)

    @api.constrains('presigned_ttl')
    def _check_ttl(self):
        for rec in self:
            if rec.presigned_ttl < 300:
                raise ValidationError(_('Pre-signed URL TTL must be at least 300 seconds (5 minutes).'))

    def write(self, vals):
        res = super().write(vals)
        self.env.registry.clear_cache()
        return res

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        self.env.registry.clear_cache()
        return res

    def unlink(self):
        res = super().unlink()
        self.env.registry.clear_cache()
        return res

    def action_test_connection(self):
        self.ensure_one()
        try:
            client = self._build_s3_client()
            client.head_bucket(Bucket=self.bucket_name)

            probe_key = '.odoo_s3_probe'
            client.put_object(
                Bucket=self.bucket_name,
                Key=probe_key,
                Body=b'odoo_s3_test',
                ContentType='text/plain',
            )
            client.delete_object(Bucket=self.bucket_name, Key=probe_key)

            self.sudo().write({'state': 'connected'})
            self.env['aws.s3.log'].sudo().create({
                'name': 'Connection Test',
                'attachment_name': 'N/A',
                's3_key': 'N/A',
                'status': 'success',
                'message': f'Connected to S3 bucket: {self.bucket_name} ({self.region_name})',
            })
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Connection Successful'),
                    'message': _('Successfully connected to S3 bucket: %s') % self.bucket_name,
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as e:
            self.sudo().write({'state': 'failed'})
            self.env['aws.s3.log'].sudo().create({
                'name': 'Connection Test',
                'attachment_name': 'N/A',
                's3_key': 'N/A',
                'status': 'failed',
                'message': f'Connection failed: {e}',
            })
            raise UserError(_('S3 Connection Failed: %s') % str(e))

    def action_activate(self):
        self.ensure_one()
        if self.state != 'connected':
            raise UserError(_('Please test the connection successfully before activating.'))
        self.write({'is_active': True})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('S3 Storage Activated'),
                'message': _('All new attachments will now be stored in AWS S3.'),
                'type': 'success',
                'sticky': True,
            }
        }

    def action_deactivate(self):
        self.ensure_one()
        self.write({'is_active': False})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('S3 Storage Deactivated'),
                'message': _('New attachments will now use Odoo local filestore.'),
                'type': 'warning',
                'sticky': False,
            }
        }

    def action_open_migration_wizard(self):
        wizard = self.env['aws.s3.migration'].create({'config_id': self.id})
        return {
            'name': _('Migrate Existing Files to S3'),
            'type': 'ir.actions.act_window',
            'res_model': 'aws.s3.migration',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _build_s3_client(self):
        import boto3
        from botocore.config import Config as BotoConfig
        return boto3.client(
            's3',
            aws_access_key_id=self.aws_access_key,
            aws_secret_access_key=self.aws_secret_key,
            config=BotoConfig(
                region_name=self.region_name,
                signature_version='s3v4',
                retries={'max_attempts': 3, 'mode': 'adaptive'},
                max_pool_connections=20,
            ),
        )
