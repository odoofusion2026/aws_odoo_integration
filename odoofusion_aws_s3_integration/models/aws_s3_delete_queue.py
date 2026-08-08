# -*- coding: utf-8 -*-
# Author: Metamorphosis, Joyanto

import logging
import datetime
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)

S3_BATCH_DELETE_MAX = 1000


class AwsS3DeleteQueue(models.Model):
    _name = 'aws.s3.delete.queue'
    _description = 'AWS S3 Pending Deletion Queue'
    _order = 'id asc'

    s3_key = fields.Char(
        string='S3 Object Key',
        required=True,
        index=True,
        help='The S3 object key (without s3:// prefix) queued for deletion.',
    )
    bucket_name = fields.Char(
        string='S3 Bucket Name',
        help='The S3 bucket name from which this object should be deleted.',
    )
    state = fields.Selection(
        selection=[
            ('pending', 'Pending'),
            ('done', 'Deleted'),
            ('failed', 'Failed'),
        ],
        string='Status',
        default='pending',
        index=True,
    )
    retry_count = fields.Integer(string='Retry Count', default=0)
    error_msg = fields.Text(string='Last Error Message')

    @api.model
    def action_process_delete_queue(self):
        client, config = self.env['ir.attachment']._get_global_s3_client()
        if not client:
            _logger.debug('S3 delete queue: no active S3 config, skipping.')
            return

        pending = self.search(
            [('state', '=', 'pending')],
            limit=S3_BATCH_DELETE_MAX,
            order='id asc',
        )
        if not pending:
            return

        _logger.info('S3 delete queue: processing %d pending deletions.', len(pending))

        from collections import defaultdict
        bucket_groups = defaultdict(list)
        for rec in pending:
            bname = rec.bucket_name or config.bucket_name
            if bname:
                bucket_groups[bname].append(rec)

        for bname, recs in bucket_groups.items():
            objects_to_delete = [{'Key': r.s3_key} for r in recs]
            bucket_rec = self.env['aws.s3.bucket'].sudo().search([('name', '=', bname), ('is_active', '=', True)], limit=1)
            if bucket_rec:
                b_client = bucket_rec._get_s3_client(bucket_rec)
            else:
                b_client = client

            try:
                response = b_client.delete_objects(
                    Bucket=bname,
                    Delete={
                        'Objects': objects_to_delete,
                        'Quiet': False,
                    },
                )

                deleted_keys = {d['Key'] for d in response.get('Deleted', [])}
                failed_map = {
                    e['Key']: e.get('Message', 'Unknown S3 error')
                    for e in response.get('Errors', [])
                }

                done_ids = []
                failed_ids = []
                retry_ids = []

                for rec in recs:
                    if rec.s3_key in deleted_keys:
                        done_ids.append(rec.id)
                    elif rec.s3_key in failed_map:
                        if rec.retry_count >= 2:
                            failed_ids.append((rec.id, failed_map[rec.s3_key]))
                        else:
                            retry_ids.append((rec.id, failed_map[rec.s3_key]))

                if done_ids:
                    self.browse(done_ids).write({'state': 'done'})

                for rec_id, err_msg in failed_ids:
                    self.browse(rec_id).write({
                        'state': 'failed',
                        'retry_count': 3,
                        'error_msg': err_msg,
                    })

                for rec_id, err_msg in retry_ids:
                    rec = self.browse(rec_id)
                    rec.write({
                        'retry_count': rec.retry_count + 1,
                        'error_msg': err_msg,
                    })

                _logger.info(
                    'S3 delete queue for bucket %s: %d deleted, %d failed, %d will retry.',
                    bname, len(done_ids), len(failed_ids), len(retry_ids),
                )

            except Exception as e:
                _logger.error('S3 batch delete failed for bucket %s: %s', bname, e)
                for rec in recs:
                    if rec.retry_count >= 2:
                        rec.write({'state': 'failed', 'error_msg': str(e)})
                    else:
                        rec.write({
                            'retry_count': rec.retry_count + 1,
                            'error_msg': str(e),
                        })

    @api.model
    def action_clean_done(self):
        cutoff = fields.Datetime.now() - datetime.timedelta(days=7)
        old_done = self.search([
            ('state', '=', 'done'),
            ('write_date', '<', cutoff),
        ])
        if old_done:
            _logger.info('S3 delete queue: cleaning %d done records.', len(old_done))
            old_done.unlink()
