import boto3
import logging
from botocore.exceptions import ClientError
import json

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize S3 and SQS clients
s3 = boto3.client('s3')
sqs = boto3.client('sqs')

# Define the SQS queue URL and the message group ID
SQS_QUEUE_URL = 'https://sqs.eu-central-1.amazonaws.com/380892414183/hell-insek-event-broker.fifo'
MESSAGE_GROUP_ID = 'INVOICE_SENDER'

def lambda_handler(event, context):
    try:
        for record in event['Records']:
            process_s3_event(record)

        return {
            'statusCode': 200,
            'body': "All records processed successfully."
        }

    except Exception as e:
        logger.error(f"Error processing event: {str(e)}")
        return {
            'statusCode': 500,
            'body': f"Error processing records: {str(e)}"
        }


def process_s3_event(record):
    bucket_name = record['s3']['bucket']['name']
    object_key = record['s3']['object']['key']
    logger.info(f"File upload detected - Bucket: {bucket_name}, File Name: {object_key}")

    # Retrieve metadata from the uploaded file using head_object
    response = s3.head_object(Bucket=bucket_name, Key=object_key)
    metadata = response['Metadata']
    order_number = metadata.get('order_number') or "-"
    customer_email = metadata.get('customer_email') or "-"

    if not order_number or not customer_email:
        logger.error(f"Missing metadata - Bucket: {bucket_name}, File Name: {object_key} - Order Number: {order_number}, Customer Email: {customer_email}")
        return

    logger.info(f"Metadata retrieved - Order Number: {order_number}, Customer Email: {customer_email}")

    # Send message to the SQS queue
    send_message_to_sqs(order_number, customer_email)


def send_message_to_sqs(order_number, customer_email):
    try:
        message_body = json.dumps({
            "orderNumber": order_number,
            "customerEmail": customer_email
        })

        response = sqs.send_message(
            QueueUrl=SQS_QUEUE_URL,
            MessageBody=message_body,
            MessageGroupId=MESSAGE_GROUP_ID,
            MessageDeduplicationId=order_number
        )

        logger.info(f"Message sent to SQS! Message ID: {response['MessageId']}")
    except ClientError as e:
        logger.error(f"Error sending message to SQS: {str(e)}")

