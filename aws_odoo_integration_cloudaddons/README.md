# Cloud Storage | AWS S3 Integration

This module seamlessly integrates Odoo 18 attachments with AWS S3 storage, enabling database size reduction, redundancy, and a modern file explorer inside Odoo.

## Core Features

1. **Auto Attachment Sync**
   - Automatically synchronizes Odoo attachments to AWS S3.
   
2. **Three Storage Modes (Per Model)**
   - **AWS S3 Only**: Uploads binary content to S3, updates the Odoo attachment to a dummy 0kb reference (`s3://...`), and deletes the local Odoo filestore file to save disk space.
   - **Dual Storage**: Stores the file in the Odoo local filestore AND uploads a duplicate to AWS S3 (ideal for high-compliance environments).
   - **Odoo Only**: Keeps files strictly in Odoo, bypassing S3 sync.

3. **Dynamic Folder Routing (3-tier)**
   - Pre-configured dynamic path routing for key Odoo models:
     - **CRM** (`crm.lead`): `CRM/<Lead Name>/<Filename>`
     - **Sales** (`sale.order`): `Sales/<Partner Name>/<Order Reference>/<Filename>`
     - **Accounting** (`account.move`): `Accounting/<Partner Name>/<Invoice Number>/<Filename>`
     - **Purchase** (`purchase.order`): `Purchase/<Partner Name>/<Order Reference>/<Filename>`
     - **HR** (`hr.employee`): `HR/<Employee Name>/<Filename>`
     - **Project** (`project.task`): `Projects/<Project Name>/<Task Name>/<Filename>`
     - **Helpdesk** (`helpdesk.ticket`): `Helpdesk/<Ticket Name>/<Filename>`
     - **Inventory** (`stock.picking`): `Inventory/<Picking Name>/<Filename>`
     - *Fallback for other models*: `Others/<Model Name>/<Record ID or Display Name>/<Filename>`

4. **S3 File Explorer**
   - Browse files and folders on your configured S3 buckets directly inside Odoo.
   - Click folders to open sub-directories.
   - Click files to download them locally via temporary streaming buffers.
   - Delete files from S3 directly from the Odoo interface.

5. **Activity Log Terminal**
   - Audit trail of all S3 operations (Upload, Read, Fallback, Delete, Connection Test) with status, timestamp, key name, model, and message details.

6. **Monitoring Dashboard**
   - Live KPI cards showcasing active buckets count, rules configured, sync success rate, and sync failures.

7. **Bulk Migration Tool**
   - Migrate existing local files to AWS S3 for any configured model rule.

---

## Configuration & Usage Guide

### Step 1: AWS Credentials & S3 Bucket Setup
1. Create a Bucket in S3 (e.g. `my-odoo-company-files`).
2. Make sure the IAM User has the necessary permissions to read/write/delete objects in the bucket:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": [
           "s3:GetObject",
           "s3:PutObject",
           "s3:DeleteObject",
           "s3:ListBucket",
           "s3:GetBucketLocation",
           "s3:HeadObject"
         ],
         "Resource": [
           "arn:aws:s3:::my-odoo-company-files",
           "arn:aws:s3:::my-odoo-company-files/*"
         ]
       }
     ]
   }
   ```

### Step 2: Configure in Odoo
1. Go to **AWS S3** → **Configuration** → **Buckets Setup**.
2. Create a new record:
   - **Bucket Name**: `my-odoo-company-files`
   - **AWS Region**: `ap-southeast-1` (or your nearest AWS region)
   - **Access Key ID**: `YOUR_ACCESS_KEY`
   - **Secret Access Key**: `YOUR_SECRET_ACCESS_KEY`
3. Save and click **Test Connection**. A success badge (`Connected`) will appear.

### Step 3: Configure Model Rules
1. Go to **AWS S3** → **Configuration** → **Sync Rules**.
2. Create rules for your models (e.g., `sale.order`):
   - **Model**: `sale.order`
   - **Storage Mode**: `AWS S3 Only`
   - **Root Folder**: `Sales/`
   - **AWS S3 Bucket**: Select your bucket configuration.
3. Save the rule.

### Step 4: Test Uploads
- Navigate to a Sale Order, upload an attachment in the Chatter.
- The attachment will be uploaded to S3 under `Sales/<Customer Name>/<Order Reference>/<Filename>`.
- The Odoo attachment record's file size is updated, and the backend retrieves it on-demand from S3 whenever accessed.

### Step 5: Bulk Migration of Existing Files
- Open a sync rule and click the **Bulk Migrate Attachments to S3** button.
- All historical attachments for that model will automatically be uploaded to S3, with the local files cleaned up if the mode is `S3 Only`.
