# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class AwsS3Bucket(models.Model):
    _name = 'aws.s3.bucket'
    _description = 'AWS S3 Bucket Configuration'
    _order = 'id desc'

    name = fields.Char(string='Bucket Name', required=True, help="Globally unique name of the AWS S3 Bucket.")
    region_name = fields.Char(string='AWS Region', default='ap-southeast-1', required=True, help="AWS S3 Region (e.g. ap-southeast-1, us-east-1).")
    aws_access_key_id = fields.Char(string='Access Key ID', required=True)
    aws_secret_access_key = fields.Char(string='Secret Access Key', required=True)
    is_active = fields.Boolean(string='Active', default=True)
    state = fields.Selection([
        ('draft', 'Not Tested'),
        ('connected', 'Connected'),
        ('failed', 'Connection Failed')
    ], string='Status', default='draft', readonly=True)

    @api.model
    def _get_s3_client(self, bucket):
        import boto3
        from botocore.config import Config
        config = Config(
            region_name=bucket.region_name,
            signature_version='s3v4'
        )
        return boto3.client(
            's3',
            aws_access_key_id=bucket.aws_access_key_id,
            aws_secret_access_key=bucket.aws_secret_access_key,
            config=config
        )

    def action_test_connection(self):
        self.ensure_one()
        try:
            client = self._get_s3_client(self)
            # Verify bucket existence and permission
            client.head_bucket(Bucket=self.name)
            self.write({'state': 'connected'})
            
            # Log connection success
            self.env['aws.s3.log'].sudo().create({
                'name': 'Connection Test',
                'attachment_name': 'N/A',
                's3_key': 'N/A',
                'status': 'success',
                'message': f"Successfully connected to AWS S3 Bucket: {self.name} ({self.region_name})"
            })
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Connection Success'),
                    'message': _('Successfully connected to AWS S3 Bucket: %s') % self.name,
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as e:
            self.write({'state': 'failed'})
            # Log connection failure
            self.env['aws.s3.log'].sudo().create({
                'name': 'Connection Test',
                'attachment_name': 'N/A',
                's3_key': 'N/A',
                'status': 'failed',
                'message': f"AWS S3 Connection Failed for Bucket {self.name}: {str(e)}"
            })
            raise UserError(_("AWS S3 Connection Failed: %s") % str(e))
