# Cloud Storage | AWS S3 Integration — Universal Offload (Odoo 19)

**Version**: 19.0.2.0.0  
**Author**: Metamorphosis, Joyanto  
**License**: OPL-1  

## Overview
Universal AWS S3 Storage Backend for Odoo 19. Offloads ALL binary files, images, product images, Chatter attachments, and invoice PDFs to AWS S3 automatically. Zero Odoo local disk usage.

## Key Features
- **Universal Storage Engine**: Overrides Odoo `ir.attachment` extension points (`_file_read`, `_file_write`, `_file_delete`, `_to_http_stream`).
- **Zero N+1 Queries**: Config cached via ORM cache, thread-local boto3 pool, in-process pre-signed URL caching (55-min TTL), and batched S3 deletions (1,000 objects per API call).
- **Transactional Safety**: S3 deletions queued and executed after DB commit via cron.
- **Background Migration**: Wizard for batch migration of existing attachments without downtime.
- **S3 File Explorer & Live Dashboard**: Native Odoo 19 dashboard and S3 bucket file explorer using `<list>` views.
