# -*- coding: utf-8 -*-
# Author: Metamorphosis, Joyanto

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class AwsS3FileExplorer(models.TransientModel):
    _name = 'aws.s3.file.explorer'
    _description = 'AWS S3 File Explorer'

    bucket_id = fields.Many2one('aws.s3.bucket', string='AWS S3 Bucket', required=True, domain=[('is_active', '=', True)])
    folder_path = fields.Char(string='Current Folder Path', default='', readonly=True)
    item_ids = fields.One2many('aws.s3.file.explorer.item', 'explorer_id', string='Files & Folders', readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        records = super(AwsS3FileExplorer, self.with_context(skip_load_items=True)).create(vals_list)
        for record in records:
            if record.bucket_id:
                record.with_context(skip_load_items=True).load_items()
        return records

    def write(self, vals):
        if self.env.context.get('skip_load_items'):
            return super(AwsS3FileExplorer, self).write(vals)
        res = super(AwsS3FileExplorer, self).write(vals)
        if 'bucket_id' in vals or 'folder_path' in vals:
            for record in self:
                record.with_context(skip_load_items=True).load_items()
        return res

    @api.model
    def action_open_explorer(self):
        bucket = self.env['aws.s3.bucket'].search([('is_active', '=', True)], limit=1)
        if not bucket:
            raise UserError(_("Please configure and activate at least one AWS S3 Bucket first."))
        explorer = self.create({
            'bucket_id': bucket.id,
            'folder_path': '',
        })
        return {
            'name': 'AWS S3 File Explorer',
            'type': 'ir.actions.act_window',
            'res_model': 'aws.s3.file.explorer',
            'res_id': explorer.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def load_items(self):
        if not self.bucket_id:
            return
        
        self.item_ids = [(5, 0, 0)]
        
        try:
            client = self.bucket_id._get_s3_client(self.bucket_id)
            prefix = self.folder_path or ''
            
            response = client.list_objects_v2(
                Bucket=self.bucket_id.name,
                Prefix=prefix,
                Delimiter='/'
            )
            
            new_items = []
            
            if prefix:
                parts = prefix.rstrip('/').split('/')
                if len(parts) > 1:
                    parent_path = '/'.join(parts[:-1]) + '/'
                else:
                    parent_path = ''
                new_items.append((0, 0, {
                    'name': '.. (Parent Directory)',
                    'key': parent_path,
                    'type': 'folder',
                    'size': '',
                    'last_modified': False,
                }))
            
            for folder in response.get('CommonPrefixes', []):
                full_prefix = folder.get('Prefix')
                folder_name = full_prefix.rstrip('/').split('/')[-1] + '/'
                new_items.append((0, 0, {
                    'name': folder_name,
                    'key': full_prefix,
                    'type': 'folder',
                    'size': '',
                    'last_modified': False,
                }))
            
            for content in response.get('Contents', []):
                key = content.get('Key')
                if key == prefix:
                    continue
                file_name = key.split('/')[-1]
                if not file_name:
                    continue
                size_bytes = content.get('Size', 0)
                
                if size_bytes < 1024:
                    size_str = f"{size_bytes} B"
                elif size_bytes < 1024 * 1024:
                    size_str = f"{size_bytes / 1024:.1f} KB"
                else:
                    size_str = f"{size_bytes / (1024 * 1024):.1f} MB"
                    
                last_modified = content.get('LastModified')
                if last_modified:
                    last_modified = last_modified.replace(tzinfo=None)

                new_items.append((0, 0, {
                    'name': file_name,
                    'key': key,
                    'type': 'file',
                    'size': size_str,
                    'last_modified': last_modified,
                }))
            
            self.item_ids = new_items
        except Exception as e:
            raise UserError(_("Failed to fetch files from S3: %s") % str(e))

    def action_refresh(self):
        self.load_items()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'aws.s3.file.explorer',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }


class AwsS3FileExplorerItem(models.TransientModel):
    _name = 'aws.s3.file.explorer.item'
    _description = 'AWS S3 File Explorer Item'

    explorer_id = fields.Many2one('aws.s3.file.explorer', string='Explorer')
    name = fields.Char(string='Name', required=True)
    key = fields.Char(string='Full Key', required=True)
    type = fields.Selection([('file', 'File'), ('folder', 'Folder')], string='Type', required=True)
    size = fields.Char(string='Size')
    last_modified = fields.Datetime(string='Last Modified')

    def action_open_folder(self):
        self.ensure_one()
        if self.type != 'folder':
            return
        
        explorer = self.explorer_id
        explorer.write({'folder_path': self.key})
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'aws.s3.file.explorer',
            'res_id': explorer.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_download_file(self):
        self.ensure_one()
        if self.type != 'file':
            return
        
        explorer = self.explorer_id
        try:
            client = explorer.bucket_id._get_s3_client(explorer.bucket_id)
            response = client.get_object(Bucket=explorer.bucket_id.name, Key=self.key)
            file_data = response['Body'].read()
            
            attachment = self.env['ir.attachment'].create({
                'name': self.name,
                'type': 'binary',
                'raw': file_data,
                'public': True,
            })
            
            return {
                'type': 'ir.actions.act_url',
                'url': f'/web/content/{attachment.id}?download=true',
                'target': 'new',
            }
        except Exception as e:
            raise UserError(_("Failed to download file from S3: %s") % str(e))

    def action_delete_file(self):
        self.ensure_one()
        explorer = self.explorer_id
        try:
            client = explorer.bucket_id._get_s3_client(explorer.bucket_id)
            client.delete_object(Bucket=explorer.bucket_id.name, Key=self.key)
            
            self.env['aws.s3.log'].sudo().create({
                'name': 'File Explorer Delete',
                'attachment_name': self.name,
                's3_key': self.key,
                'status': 'success',
                'message': f"Deleted from S3 bucket {explorer.bucket_id.name} via File Explorer"
            })
            
            explorer.load_items()
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'aws.s3.file.explorer',
                'res_id': explorer.id,
                'view_mode': 'form',
                'target': 'new',
            }
        except Exception as e:
            raise UserError(_("Failed to delete file from S3: %s") % str(e))
