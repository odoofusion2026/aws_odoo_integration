# -*- coding: utf-8 -*-
# Author: Metamorphosis, Joyanto

import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

BATCH_SIZE = 200


class AwsS3Migration(models.TransientModel):
    _name = 'aws.s3.migration'
    _description = 'AWS S3 Bulk Migration Wizard'

    config_id = fields.Many2one(
        'aws.s3.config',
        string='S3 Configuration',
        required=True,
        domain=[('is_active', '=', True)],
    )

    total_local = fields.Integer(
        string='Local Filestore Files',
        compute='_compute_migration_stats',
    )
    total_db = fields.Integer(
        string='DB Binary Files',
        compute='_compute_migration_stats',
    )
    total_already_s3 = fields.Integer(
        string='Already in S3',
        compute='_compute_migration_stats',
    )
    total_all = fields.Integer(
        string='Total Attachments',
        compute='_compute_migration_stats',
    )

    migration_log = fields.Text(
        string='Last Migration Run Log',
        readonly=True,
    )

    def _compute_migration_stats(self):
        for rec in self:
            Attachment = self.env['ir.attachment'].sudo()
            rec.total_local = Attachment.search_count([
                ('store_fname', '!=', False),
                ('store_fname', 'not like', 's3://%'),
            ])
            rec.total_db = Attachment.search_count([
                ('db_datas', '!=', False),
                ('store_fname', '=', False),
            ])
            rec.total_already_s3 = Attachment.search_count([
                ('store_fname', 'like', 's3://%'),
            ])
            rec.total_all = Attachment.search_count([])

    def action_start_background_migration(self):
        self.ensure_one()
        if not self.config_id.is_active:
            raise UserError(_('The selected S3 config is not active. Please activate it first.'))

        cron = self.env.ref(
            'odoofusion_aws_s3_integration.ir_cron_s3_migration',
            raise_if_not_found=False,
        )
        if cron:
            cron.write({'active': True})

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Background Migration Started'),
                'message': _(
                    'Files will be migrated to S3 in batches of %d. '
                    'Monitor progress from the dashboard.'
                ) % BATCH_SIZE,
                'type': 'success',
                'sticky': True,
            }
        }

    def action_run_batch_now(self):
        self.ensure_one()
        success, failed, log = self._process_migration_batch()
        self.write({'migration_log': log})

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Batch Complete'),
                'message': _('%d migrated, %d failed. Check the log below.') % (success, failed),
                'type': 'success' if failed == 0 else 'warning',
                'sticky': False,
            }
        }

    @api.model
    def action_cron_migrate_batch(self):
        success, failed, log = self._process_migration_batch()
        _logger.info('S3 migration cron: %d migrated, %d failed.', success, failed)

        remaining = self.env['ir.attachment'].sudo().search_count([
            '|',
            ('store_fname', 'not like', 's3://%'),
            ('db_datas', '!=', False),
            ('store_fname', '=', False),
        ])

        if remaining == 0:
            cron = self.env.ref(
                'odoofusion_aws_s3_integration.ir_cron_s3_migration',
                raise_if_not_found=False,
            )
            if cron:
                cron.write({'active': False})
            _logger.info('S3 migration complete! Cron deactivated.')

    @api.model
    def _process_migration_batch(self):
        IrAttachment = self.env['ir.attachment'].sudo()
        client, config = IrAttachment._get_global_s3_client()

        if not client:
            return 0, 0, 'No active S3 configuration found.'

        log_lines = []
        success_count = 0
        failed_count = 0

        db_attachments = IrAttachment.search([
            ('db_datas', '!=', False),
            ('store_fname', '=', False),
            ('store_fname', 'not like', 's3://%'),
        ], limit=BATCH_SIZE)

        for attach in db_attachments:
            try:
                data = attach.raw
                if not data:
                    continue

                checksum = attach.checksum or attach._compute_checksum(data)
                new_fname = IrAttachment._file_write(data, checksum)

                if new_fname.startswith('s3://'):
                    self.env.cr.execute(
                        """UPDATE ir_attachment
                           SET store_fname = %s, db_datas = NULL, is_s3_stored = TRUE
                           WHERE id = %s""",
                        (new_fname, attach.id)
                    )
                    success_count += 1
                    log_lines.append(f'[OK] DB→S3: {attach.name} (id={attach.id})')
                else:
                    failed_count += 1
                    log_lines.append(f'[FAIL] DB→S3 fallback to local: {attach.name}')

            except Exception as e:
                failed_count += 1
                log_lines.append(f'[ERROR] {attach.name}: {e}')
                _logger.error('Migration failed for attachment %d: %s', attach.id, e)

        remaining_limit = BATCH_SIZE - len(db_attachments)
        if remaining_limit > 0:
            local_attachments = IrAttachment.search([
                ('store_fname', '!=', False),
                ('store_fname', 'not like', 's3://%'),
            ], limit=remaining_limit)

            for attach in local_attachments:
                try:
                    old_fname = attach.store_fname
                    data = attach._file_read(old_fname)
                    if not data:
                        log_lines.append(f'[SKIP] Empty file: {attach.name}')
                        continue

                    checksum = attach.checksum or attach._compute_checksum(data)
                    new_fname = IrAttachment._file_write(data, checksum)

                    if new_fname.startswith('s3://'):
                        self.env.cr.execute(
                            """UPDATE ir_attachment
                               SET store_fname = %s, is_s3_stored = TRUE
                               WHERE id = %s""",
                            (new_fname, attach.id)
                        )
                        IrAttachment._mark_for_gc(old_fname)
                        success_count += 1
                        log_lines.append(f'[OK] Local→S3: {attach.name} (id={attach.id})')
                    else:
                        failed_count += 1
                        log_lines.append(f'[FAIL] Local→S3 fallback: {attach.name}')

                except Exception as e:
                    failed_count += 1
                    log_lines.append(f'[ERROR] {attach.name}: {e}')
                    _logger.error('Migration failed for attachment %d: %s', attach.id, e)

        log_text = '\n'.join(log_lines) or 'No files found to migrate in this batch.'
        return success_count, failed_count, log_text
