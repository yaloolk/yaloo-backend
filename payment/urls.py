# payment/urls.py

from django.urls import path
from . import views

urlpatterns = [
    path('create-intent/',        views.create_payment_intent,      name='payment-create-intent'),
    path('cancellation-preview/', views.cancellation_preview,       name='cancellation-preview'),
    path('cancel/',               views.cancel_booking_with_refund, name='payment-cancel'),
    path('webhook/',              views.stripe_webhook,             name='stripe-webhook'),
    path('policy/',               views.get_cancellation_policy,    name='cancellation-policy-get'),
    path('policy/update/',        views.update_cancellation_policy, name='cancellation-policy-update'),
]