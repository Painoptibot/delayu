from django.urls import path

from delayu import views_service, views_service_account, views_service_office, views_service_process

urlpatterns = [
    path("service/", views_service.ServiceHubView.as_view(), name="service-hub"),
    path("service/customers/", views_service.ServiceCustomerListView.as_view(), name="service-customers"),
    path("service/deals/", views_service.ServiceDealBoardView.as_view(), name="service-deals"),
    path("service/quotes/", views_service.ServiceQuoteView.as_view(), name="service-quotes"),
    path(
        "service/customers/<int:pk>/",
        views_service.ServiceCustomerDetailView.as_view(),
        name="service-customer",
    ),
    path("service/channels/", views_service.ServiceChannelListView.as_view(), name="service-channels"),
    path("service/inbox/", views_service_account.ServiceInboxView.as_view(), name="service-inbox"),
    path("service/tasks/", views_service_account.ServiceTaskListView.as_view(), name="service-tasks"),
    path("service/queue/", views_service_process.ServiceQueueView.as_view(), name="service-queue"),
    path("service/playbooks/", views_service_process.ServicePlaybookView.as_view(), name="service-playbooks"),
    path("service/report/", views_service_account.ServiceReportView.as_view(), name="service-report"),
    path("service/fields/", views_service_account.ServiceFieldListView.as_view(), name="service-fields"),
    path("service/forms/", views_service_account.ServiceFormListView.as_view(), name="service-forms"),
    path("service/phones/", views_service_account.ServicePhoneListView.as_view(), name="service-phones"),
    path("service/calendars/", views_service_office.ServiceCalendarView.as_view(), name="service-calendars"),
    path("service/workflows/", views_service_office.ServiceWorkflowView.as_view(), name="service-workflows"),
    path("service/funnels/", views_service_office.ServiceFunnelView.as_view(), name="service-funnels"),
    path("service/mailings/", views_service_office.ServiceMailingView.as_view(), name="service-mailings"),
    path("service/ads/", views_service_office.ServiceAdView.as_view(), name="service-ads"),
    path("service/invoices/", views_service_office.ServiceInvoiceView.as_view(), name="service-invoices"),
    path("service/media/", views_service_office.ServiceMediaView.as_view(), name="service-media"),
    path("service/objects/", views_service.ServiceObjectListView.as_view(), name="service-objects"),
    path(
        "service/objects/<int:pk>/",
        views_service.ServiceObjectDetailView.as_view(),
        name="service-object",
    ),
]
