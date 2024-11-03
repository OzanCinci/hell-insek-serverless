import requests
import json
import pytz
import locale
import boto3
import logging
from datetime import datetime
from io import BytesIO

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)
# set up s3
s3 = boto3.client('s3')


class InvoiceGenerator:
    URL = "https://invoice-generator.com"
    DATE_FORMAT = "%d/%m/%y %H:%M:%S"
    LOCALE = "de_DE"
    TIMEZONE = "Europe/Berlin"
    TEMPLATE_PARAMETERS = [
        "header", "to_title", "ship_to_title", "invoice_number_title", "date_title",
        "payment_terms_title", "due_date_title", "purchase_order_title", "quantity_header",
        "item_header", "unit_cost_header", "amount_header", "subtotal_title", "discounts_title",
        "tax_title", "shipping_title", "total_title", "amount_paid_title", "balance_title",
        "terms_title", "notes_title",
    ]

    def __init__(self, sender, to, logo=None, ship_to=None, number=None, payments_terms=None,
                 due_date=None, notes=None, terms=None, currency="USD",
                 date=datetime.now(tz=pytz.timezone(TIMEZONE)), discounts=0, tax=0, shipping=0, amount_paid=0, tax_title=None):
        self.logo = "https://hell-insek-pdfs.s3.amazonaws.com/logo.webp"
        self.sender = sender
        self.to = to
        self.ship_to = ship_to
        self.number = number
        self.currency = currency
        self.custom_fields = []
        self.date = date
        self.payment_terms = payments_terms
        self.due_date = due_date
        self.items = []
        self.fields = {"tax": "%", "discounts": False, "shipping": False}
        #self.fields = {"tax": False, "discounts": False, "shipping": False}
        self.discounts = discounts
        self.tax = tax
        self.tax_title = tax_title
        self.shipping = shipping
        self.amount_paid = amount_paid
        self.notes = notes
        self.terms = terms
        self.template = {}

    def _to_json(self):
        locale.setlocale(locale.LC_ALL, InvoiceGenerator.LOCALE)
        object_dict = self.__dict__
        object_dict['from'] = object_dict.get('sender')
        object_dict['date'] = self.date.strftime(InvoiceGenerator.DATE_FORMAT)
        object_dict.pop('sender')
        for index, item in enumerate(object_dict['items']):
            object_dict['items'][index] = item.__dict__
        for index, custom_field in enumerate(object_dict['custom_fields']):
            object_dict['custom_fields'][index] = custom_field.__dict__
        for template_parameter, value in self.template.items():
            object_dict[template_parameter] = value
        object_dict.pop('template')
        return json.dumps(object_dict)

    def add_custom_field(self, name=None, value=None):
        self.custom_fields.append(CustomField(name=name, value=value))

    def add_item(self, name=None, quantity=0, unit_cost=0.0, description=None):
        self.items.append(Item(name=name, quantity=quantity, unit_cost=unit_cost, description=description))

    def upload_to_s3(self, s3_bucket, s3_key, order_number, customer_email):
        json_string = self._to_json()
        logger.info(f"ORDER ({order_number}): post request is starting...")

        response = requests.post(
            InvoiceGenerator.URL,
            json=json.loads(json_string),
            stream=True,
            headers={
                'Accept-Language': InvoiceGenerator.LOCALE,
                'Authorization': "Bearer "
            })

        logger.info(f"ORDER ({order_number}): response has been received...")

        if response.status_code == 200:
            logger.info(f"ORDER ({order_number}): response success starting to upload")
            pdf_stream = BytesIO(response.content)

            metadata = {
                'order_number': order_number,
                'customer_email': customer_email
            }
            s3.upload_fileobj(
                pdf_stream,
                s3_bucket,
                s3_key,
                ExtraArgs={
                    'ContentType': 'application/pdf',
                    'Metadata': metadata
                }
            )
            logger.info(f"ORDER ({order_number}): upload success")
        else:
            logger.info(f"ORDER ({order_number}): response fail incoive api error")
            raise Exception(
                f"Invoice download request returned the following message: {response.json()} Response code = {response.status_code}")

    def set_template_text(self, template_parameter, value):
        if template_parameter in InvoiceGenerator.TEMPLATE_PARAMETERS:
            self.template[template_parameter] = value
        else:
            raise ValueError(f"The parameter {template_parameter} is not a valid template parameter.")

    def toggle_subtotal(self, tax="%", discounts=False, shipping=False):
        self.fields = {"tax": tax, "discounts": discounts, "shipping": shipping}


class Item:
    def __init__(self, name, quantity, unit_cost, description=""):
        self.name = name
        self.quantity = quantity
        self.unit_cost = unit_cost
        self.description = description


class CustomField:
    def __init__(self, name, value):
        self.name = name
        self.value = value

def lambda_handler(event, context):
    try:
        logger.info(f"Received event: {json.dumps(event)}")

        for record in event['Records']:
            create_invoice_by_order(record)

        return {
            'statusCode': 200,
            'body': json.dumps(f"All invoices successfully generated and uploaded")
        }

    except Exception as e:
        logger.info(f"Something went wrong: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps(f"Error generating invoices: {str(e)}")
        }


def create_invoice_by_order(record):
    body = json.loads(record['body'])
    customer = body['customer']
    order = body['order']
    logger.info(f"RECEIVED ORDER: {order['orderNumber']}")
    logger.info(f"ORDER ({order['orderNumber']}): creating invoice")

    # Adjust date parsing to handle nanoseconds
    date_str = order['orderDate'][:26] + "Z"  # Trim to microseconds

    invoice = InvoiceGenerator(
        sender="""
                    Hell Insekten & Sonnenschutz
                    Lochfeldstr.30
                    76437 Rastatt
                    Tel.: 017662960342
                    info@hell-insektenschutz.de
                    www.hell-insekten-sonnenschutz.com
                """,
        to=f"{customer['fullName']}\n{customer['address']}",
        number=order['orderNumber'],
        date=datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S.%fZ"),
        tax=order['tax']['percentage'],
        shipping=order['shippingPrice'],
        amount_paid=0,
        currency="EUR",
        tax_title="Umsatzsteuer",
        notes=f"""
                    RECHNUNG: {order['orderNumber']}
                    Diese Rechnung wurde für die Bestellung: {order['orderNumber']} erstellt.
                    Vielen Dank für die gute Zusammenarbeit.
                """,
        terms="""
                    Aufgrund der Maßanfertigung sind alle Elemente vom Umtausch ausgeschlossen.
                    Zahlungsbedingung: Zahlung bereits erfolgt.
                    
                    
                    Dies ist das Ende der Rechnung.
                """
    )
    logger.info(f"ORDER ({order['orderNumber']}): adding items")
    for item in order['items']:
        invoice.add_item(name=item['title'], quantity=item['quantity'], unit_cost=item['unitPrice'],
                         description=item['description'])
    current_time = datetime.now().strftime(InvoiceGenerator.DATE_FORMAT)
    invoice.add_custom_field('Rechnungsdatum', current_time)
    invoice.add_custom_field('USt-IdNr. und Steuernummer',
                             """
                                DE354909066
                                3910726980
                            """)
    invoice.add_custom_field('Bankverbindung',
                             """
                                Hakan Aydin\n 
                                Volksbank pur\n
                                IBAN:DE25 6619 
                                0000 0010 6615 10\n
                                BIC:GENODE61KA1
                            """)
    s3_bucket = 'hell-insekten-sonnenschutz-invoices-pdf'
    s3_key = f"{order['orderNumber']}.pdf"
    invoice.upload_to_s3(s3_bucket=s3_bucket, s3_key=s3_key, order_number=order['orderNumber'], customer_email=customer['email'])
