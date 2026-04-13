# core/urls.py

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from payment import views as payment_views

def root_view(request):
    """Root endpoint - shows API is running"""
    return JsonResponse({
        'status': 'online',
        'message': 'Yaloo API is running',
        'endpoints': {
            'health': '/api/accounts/health/',
            'admin': '/admin/',
            'api': '/api/accounts/',
        }
    })

urlpatterns = [
    path('', root_view, name='root'),  # Add this
    path('admin/', admin.site.urls),
    path('api/accounts/', include('accounts.urls')),
    path('api/bookings/', include('bookings.urls')),
    # path('api/payment/webhook/', csrf_exempt(payment_views.stripe_webhook)),
    path('api/payment/', include('payment.urls')),
    
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)