"""
Razorpay integration for CoursePayment. Creates orders and verifies payment.
"""
import razorpay
from django.conf import settings


class RazorpayService:
    def __init__(self):
        key = getattr(settings, 'RAZORPAY_KEY', '') or getattr(settings, 'RAZORPAY_API_KEY', '')
        secret = getattr(settings, 'RAZORPAY_SECRET', '') or getattr(settings, 'RAZORPAY_API_SECRET', '')
        self.client = razorpay.Client(auth=(key, secret))

    def create_order(self, order_amount=0, order_receipt=''):
        """order_amount in paise. Returns dict with 'id' (order_id)."""
        data = {
            'amount': order_amount,
            'currency': 'INR',
            'receipt': order_receipt,
        }
        response = self.client.order.create(data=data)
        return response

    def verify_payment(self, order_payment):
        """Verify signature and payment status/amount. order_payment has gateway_* and get_gateway_amount()."""
        try:
            signature_ok = self.get_signature_status(order_payment)
            status_ok = self.get_payment_status(order_payment)
            return signature_ok and status_ok
        except Exception:
            return False

    def get_signature_status(self, order_payment):
        d = {
            'razorpay_payment_id': order_payment.gateway_payment_id,
            'razorpay_order_id': order_payment.gateway_order_id,
            'razorpay_signature': order_payment.gateway_signature,
        }
        self.client.utility.verify_payment_signature(d)
        return True

    def get_payment_status(self, order_payment):
        payment_id = order_payment.gateway_payment_id
        amount_paise = order_payment.get_gateway_amount()
        detail = self.client.payment.fetch(payment_id)
        status = detail.get('status')
        amount_ok = int(detail.get('amount', 0)) == amount_paise
        return (status in ('captured', 'authorized')) and amount_ok
