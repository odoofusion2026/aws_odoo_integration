# -*- coding: utf-8 -*-
from odoo import models, fields

class AwsS3Log(models.Model):
    _name = 'aws.s3.log'
    _description = 'AWS S3 Sync Activity Log'
    _order = 'id desc'

    name = fields.Char(string='Action/Operation', required=True, index=True)
    attachment_name = fields.Char(string='Attachment Name', index=True)
    res_model = fields.Char(string='Odoo Model', index=True)
    res_id = fields.Integer(string='Record ID', index=True)
    s3_key = fields.Char(string='S3 Object Key')
    status = fields.Selection([
        ('success', 'Success'),
        ('failed', 'Failed')
    ], string='Status', required=True, index=True)
    message = fields.Text(string='Message/Details')
    create_date = fields.Datetime(string='Timestamp', readonly=True)
