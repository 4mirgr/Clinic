from django.urls import path
from django.views.generic import RedirectView
from clinic import views, views_auth, views_preferences

urlpatterns = [
    path('dash', RedirectView.as_view(url='/dash/', permanent=False)),
    path('dash/', views.dashboard, name='dashboard'),
    path('dash/login/', views_auth.login_choice, name='login_choice'),
    path('dash/login/manager/', views_auth.portal_login, {'role':'manager'}, name='manager_login'),
    path('dash/login/secretary/', views_auth.portal_login, {'role':'secretary'}, name='secretary_login'),
    path('dash/logout/', views_auth.sign_out, name='logout'),
    path('dash/preferences/theme/', views_preferences.set_theme, name='set_theme'),
    path('dash/patients/', views.patients, name='patients'),
    path('dash/patients/new/', views.patient_new, name='patient_new'),
    path('dash/patients/<uuid:pk>/', views.patient_detail, name='patient_detail'),
    path('dash/patients/<uuid:pk>/edit/', views.patient_edit, name='patient_edit'),
    path('dash/patients/<uuid:pk>/visits/new/', views.visit_new, name='visit_new'),
    path('dash/patients/<uuid:pk>/documents/new/', views.document_new, name='document_new'),
    path('dash/documents/<uuid:pk>/download/', views.document_download, name='document_download'),
    path('dash/advice/', views.advice_list, name='advice'),
    path('dash/advice/new/', views.advice_edit, name='advice_new'),
    path('dash/advice/qr/', views.advice_qr, name='advice_qr'),
    path('dash/advice/<uuid:pk>/edit/', views.advice_edit, name='advice_edit'),
    path('dash/advice/<uuid:pk>/print/', views.advice_print, name='advice_print'),
    path('dash/activity/', views.activity, name='activity'),
]
