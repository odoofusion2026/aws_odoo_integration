{
    'name': 'Cloud Storage | AWS S3 Integration',
    'version': '1.0.0',
    'category': 'Extra Tools',
    'summary': 'Sync Odoo attachments directly to AWS S3 with multi-bucket, file explorer, activity logs, and real-time dashboard.',
    'description': """
AWS S3 Cloud Storage Integration for Odoo
=========================================
This module enables seamless storage of Odoo attachments directly in AWS S3.

Key Features:
-------------
* **Auto Attachment Sync**: Automatically sync attachments from configured models.
* **Three Storage Modes**:
  - AWS S3 Only (Saves database/filestore space, only stores 0kb URL pointers in Odoo)
  - Dual Storage (Saves both in Odoo and S3 for compliance)
  - Odoo Only (Standard Odoo behavior)
* **Built-in S3 File Explorer**: Browse, upload, download, and delete files on AWS S3 directly within Odoo.
* **Activity Log Terminal**: Real-time logging of all AWS S3 storage actions.
* **Monitoring Dashboard**: Stat widgets showcasing key metrics of sync.
* **Multi-Bucket Support**: Setup and configure multiple buckets.
* **Bulk Migration Tool**: Easily migrate existing attachments of configured models to AWS S3.
    """,
    'author': 'OdooFusion',
    'website': 'https://odoofusion.net',
    'depends': ['base', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'data/aws_s3_data.xml',
        'views/aws_s3_bucket_views.xml',
        'views/aws_s3_attachment_rule_views.xml',
        'views/aws_s3_log_views.xml',
        'views/aws_s3_dashboard_views.xml',
        'views/aws_s3_file_explorer_views.xml',
        'views/menuitems.xml',
    ],
    'installable': True,
    'application': True,
    'price': 39.00,
    'currency': 'USD',
    'license': 'OPL-1',
}

