{
    'name': 'Cloud Storage | AWS S3 Integration',
    'version': '17.0.2.0.0',
    'category': 'Extra Tools',
    'summary': (
        'Universal AWS S3 Storage Backend for Odoo 17. '
        'ALL files, images, and attachments stored in S3 automatically. '
        'Zero local disk usage. Full website & eCommerce image offloading.'
    ),
    'description': """
AWS S3 Universal Storage Backend for Odoo 17
============================================

Version 17.0.2.0.0 — Full Odoo Storage Offload Architecture

What This Module Does
---------------------
Makes AWS S3 the universal storage backend for ALL binary data in Odoo 17.
Every attachment, product image, website CMS image, chatter file, and invoice
PDF is stored exclusively in AWS S3 — Odoo only stores metadata pointers.

Architecture (v17.0.2.0.0)
--------------------------
* Global S3 Storage Engine: Overrides Odoo's officially designed extension
  points (_file_read, _file_write, _file_delete) — works for EVERY model
  automatically, no per-model rules required.
* Zero N+1 Queries:
  - S3 config cached via ORM cache
  - boto3 client pooled per OS thread
  - Pre-signed URLs cached in-process (55-minute TTL)
  - S3 deletions batched (up to 1000 per API call via delete queue)
* Transactional Safety & Graceful Fallback
* Background Migration: Batch migration wizard for existing attachments.
""",
    'author': 'OdooFusion',
    'website': 'https://odoofusion.net',
    'depends': ['base', 'mail', 'web'],
    'external_dependencies': {'python': ['boto3']},
    'data': [
        'security/ir.model.access.csv',
        'data/aws_s3_data.xml',
        'data/aws_s3_cron.xml',
        'views/aws_s3_bucket_views.xml',
        'views/aws_s3_attachment_rule_views.xml',
        'views/aws_s3_delete_queue_views.xml',
        'views/aws_s3_log_views.xml',
        'views/aws_s3_dashboard_views.xml',
        'views/aws_s3_file_explorer_views.xml',
        'views/aws_s3_config_views.xml',
        'views/aws_s3_migration_views.xml',
        'views/ir_attachment_views.xml',
        'views/menuitems.xml',
    ],
    'installable': True,
    'application': True,
    'price': 39.00,
    'currency': 'USD',
    'license': 'OPL-1',
    'images': [
        'static/description/banner.png'
    ],
}
