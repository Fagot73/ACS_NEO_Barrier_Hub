import csv

import redis
from django.contrib import admin
from django.contrib import messages
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import path, include
from django_changelist_toolbar_admin.admin import DjangoChangelistToolbarAdmin
from .models import SettingsMySQL

from pythonping import ping

from .models import *

CODE_STATUS = ['Успішний прохід', 'Піднесення', 'Прохід не відбувся', 'Нема в базі', 'Доступу до зони не має',
               'Доступу до тайм-зони не має']

CODE_TYPE_PASSAGE = ['Автоматично', 'Вручну']
METHOD = ['Готівкою', 'Карткою']
TYPE = ['Талон', 'Картка']
PURPOSE = ['Оплата', 'Доплата']

admin.site.site_header = 'ACS NEO Barrier HUB Панель адміністрування'

redis = redis.StrictRedis(
    host='127.0.0.1',
    port=6379,
    charset="utf-8",
    decode_responses=True
)


# admin.site.unregister(models.User)

class ExportCsvMixin:
    def export_as_csv(self, request, queryset):
        meta = self.model._meta
        type = str(meta)
        field_names = [field.name for field in meta.fields]
        print(field_names)
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename={}.csv'.format(meta)
        writer = csv.writer(response)

        writer.writerow(field_names)
        for obj in queryset:
            row = [getattr(obj, field) for field in field_names]

            if type == 'main.payment':
                print(row[1])
                row[2] = TYPE[row[2]]
                row[3] = METHOD[row[3]]
                row[4] = PURPOSE[row[4]]

            elif type == 'main.event':
                row[8] = CODE_STATUS[row[8]]
                row[9] = CODE_TYPE_PASSAGE[row[9]]

            row = writer.writerow(row)

        return response

    export_as_csv.short_description = "Експортувати в csv"


# Register your models here.


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ['name', 'surname']


@admin.register(Card)
class CardAdmin(DjangoChangelistToolbarAdmin, admin.ModelAdmin):
    list_display = ['user_id', 'uuid', 'group', 'status']


@admin.register(Auto)
class AutoAdmin(admin.ModelAdmin):
    list_display = ['mark', 'state_number', 'user_id']


@admin.register(TimeZone)
class TimeZoneAdmin(admin.ModelAdmin):
    list_display = ['time_start', 'time_end', 'id_zone']
    list_filter = ['time_start', 'time_end', 'id_zone']


@admin.register(Zone)
class ZoneAdmin(DjangoChangelistToolbarAdmin, admin.ModelAdmin):
    list_display = ['name_zone']
    django_changelist_toolbar_buttons = ["_import", ]

    def _import(self, request):
        return '_import'

    def get_urls(self):
        urls = super(ZoneAdmin, self).get_urls()
        custom_urls = [
            path('_import', self.import_rate, name='import_rate'),
        ]
        return custom_urls + urls

    def import_rate(self, request):
        zones_hub = Zone.objects.using('Hub').all()
        zones_local = Zone.objects.all()

        if len(zones_local) == 0:
            for zone in zones_hub.reverse():
                if not Zone.objects.filter(name_zone=zone.name_zone).exists():
                    zone.save(using='default')

        return HttpResponseRedirect("/main/zone/")

    _import.title = "IMPORT"
    _import.icon = "fas fa-file-import"


@admin.register(Event)
class EventAdmin(admin.ModelAdmin, ExportCsvMixin):
    list_display = ['surname', 'name', 'uuid', 'group', 'date', 'direction', 'status', 'type_passage', 'image_tag',
                    'sync']
    list_filter = ['type_passage', 'group', 'date', 'direction']
    search_fields = ['uuid']
    ordering = ['-date', 'surname']
    actions = []
    readonly_fields = ('image_tag',)

    def get_rangefilter_created_at_default(self, request):
        return (datetime.date.today,)

    def get_rangefilter_created_at_title(self, request, field_path):
        return 'custom title'

    def get_actions(self, request):
        actions = super(EventAdmin, self).get_actions(request)
        if request.user:
            self.actions.append("export_as_csv")
            return actions


@admin.register(Reader)
class ReaderAdmin(admin.ModelAdmin):
    list_display = ['zone', 'number_reader']


@admin.register(SettingsCamera)
class SettingsCameraAdmin(admin.ModelAdmin):
    list_display = ['ip', 'use_camera', 'use_camera_for_recognition']  # added use_camera_for_recognition

    fieldsets = (
        (None, {
            'fields': ('ip', 'port', 'login', 'password', 'brand_camera', 'use_camera', 'use_camera_for_recognition')  # added use_camera_for_recognition
        }),
        ("Налаштування камери для в'їзду/виїзду", {
            'fields': ('type_camera', 'zone')
        }))


@admin.register(SettingsMySQL)
class SettingsMySQLAdmin(admin.ModelAdmin):
    list_display = ('ip', 'login', 'database', 'use_mysql')  # 01/06/2023 Замінено 'table_name' на 'database'


@admin.register(Controller)
class ControllerAdmin(DjangoChangelistToolbarAdmin, admin.ModelAdmin):
    list_display = ['ip', 'type_controller', 'name_controller', 'state_controller', 'security_mode']
    readonly_fields = ['ip', 'state_controller', 'security_mode']
    exclude = ['state_printer']
    django_changelist_toolbar_buttons = [
        'open',
        'close',
    ]

    def open(self, request):
        return "open"

    def close(self, request):
        return 'close'

    def get_urls(self):
        urls = super(ControllerAdmin, self).get_urls()
        custom_urls = [
            path('export', self.export_settings, name='export_settings'),
            path('_import', self.import_settings, name='import_settings'),
            path('open', self.open_barrier, name='open_barrier'),
            path('close', self.close_barrier, name='close_barrier'),
        ]
        return custom_urls + urls

    def export_settings(self, request):
        readers = Reader.objects.values()
        # system_buttons = SystemButton.objects.values()
        camera_settings = list(SettingsCamera.objects.values())
        mysql_settings = SettingsMySQL.objects.values()

        readers = list(readers)
        # system_buttons = list(system_buttons)

        zone = Zone.objects.values()
        zone = list(zone)

        json_str = {'camera': camera_settings,
                    'mysql': mysql_settings[0],
                    'zone': zone,
                    'readers': readers,
                    }

        file = json.dumps(json_str, indent=4, ensure_ascii=False, sort_keys=True)

        response = HttpResponse(file, content_type='application/json')
        response['Content-Disposition'] = 'attachment; filename=settings.json'
        # self.message_user(request, f"Налаштування експортовано")
        return response

    def import_settings(self, request):
        return HttpResponseRedirect("/main/controller/1/change/")

    def open_barrier(self, request):
        redis.set('open_barrier', 1)
        event = Event()
        event.date = datetime.datetime.now()
        event.status = 0
        event.type_passage = 1
        try:
            event.save(using='Hub')
        except Exception as ex:
            event.sync = False
        event.save()
        return HttpResponseRedirect("/main/controller/")

    def close_barrier(self, request):
        redis.set('close_barrier', 1)
        return HttpResponseRedirect("/main/controller/")


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ['name_group']


# @admin.register(ParkConfig)
class ParkConfigAdmin(admin.ModelAdmin):
    list_display = ['total_seats', 'free_seats', 'company_name']

    fieldsets = (
        (None, {
            'fields': ('total_seats', 'free_seats', 'free_time', 'interval', 'print_ticket')
        }),
        ('Конструктор талону', {
            'fields': ('company_name', 'address', 'city', 'tell', 'additional_information')
        }))


# @admin.register(Diapason)
class DiapasonAdmin(admin.ModelAdmin):
    list_display = ['date_st', 'date_end', 'price', 'type']

    def save_model(self, request, obj, form, change):
        print(form)
        if str(obj.date_end) == '00:00:00':
            messages.warning(request, 'Не валідна дата. Замінено на 23:59:59')
            obj.date_end = '23:59:00'
        super(DiapasonAdmin, self).save_model(request, obj, form, change)


# @admin.register(CardRate)
class RateCardAdmin(DjangoChangelistToolbarAdmin, admin.ModelAdmin):
    list_display = ['name']
    django_changelist_toolbar_buttons = ["_import", ]

    def _import(self, request):
        return '_import'

    def get_urls(self):
        urls = super(RateCardAdmin, self).get_urls()
        custom_urls = [
            path('_import', self.import_rate, name='import_rate'),
        ]
        return custom_urls + urls

    def import_rate(self, request):
        rates_hub = CardRate.objects.using('Hub').all()
        rates_local = CardRate.objects.all()
        if len(rates_local) == 0:
            for rate in rates_hub.reverse():
                if not CardRate.objects.filter(name=rate.name).exists():
                    rate.save(using='default')

        return HttpResponseRedirect("/main/cardrate/")

    _import.title = "IMPORT"
    _import.icon = "fas fa-file-import"


# @admin.register(Rate)
class RateAdmin(DjangoChangelistToolbarAdmin, admin.ModelAdmin):
    list_display = ['name']
    django_changelist_toolbar_buttons = ["_import", ]

    def _import(self, request):
        return '_import'

    def get_urls(self):
        urls = super(RateAdmin, self).get_urls()
        custom_urls = [
            path('_import', self.import_rate, name='import_rate'),
        ]
        return custom_urls + urls

    def import_rate(self, request):
        rates_hub = Rate.objects.using('Hub').all()
        rates_local = Rate.objects.all()
        if len(rates_local) == 0:
            for rate in rates_hub.reverse():
                for diapason in rate.diapasons.all():
                    if not Diapason.objects.filter(date_st=diapason.date_st, date_end=diapason.date_end,
                                                   price=diapason.price,
                                                   type=diapason.type).exists():
                        diapason.save(using='default')

                rate.save(using='default')

        return HttpResponseRedirect("/main/rate/")

    _import.title = "IMPORT"
    _import.icon = "fas fa-file-import"

    def get_form(self, request, obj=None, **kwargs):
        try:
            if obj.name < 7:
                self.exclude = ('fine',)
            elif obj.name == 7:
                self.exclude = ('diapasons', 'max_sum_per_day',)
            elif obj.name == 8:
                self.exclude = ('diapasons', 'max_sum_per_day', 'fine',)
        finally:
            form = super(RateAdmin, self).get_form(request, obj, **kwargs)

            return form


# @admin.register(VirtualAccount)
class VirtualAccountAdmin(admin.ModelAdmin):
    list_display = ['user_id', 'date_st', 'date_end']


# @admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ['barcode', 'state_number', 'date_st', 'date_end', 'rate', 'status']
    list_filter = ['status', 'rate', 'date_st', 'sync']
    search_fields = ['barcode']


# @admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['uuid', 'payment_date', 'cashbox', 'operator', 'price', 'units', '_sum']
    list_filter = ['cashbox', 'operator', 'payment_date']
    search_fields = ['uuid']


# @admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = ['shift_open', 'shift_close', 'cashbox', 'operator', 'shift_is_close']
    search_fields = ['cashbox', 'operator']
    list_filter = ['cashbox', 'operator']


# @admin.register(TicketInSystem)
class TicketInSystemAdmin(admin.ModelAdmin):
    list_display = ['uuid', 'date_input', 'status']
    list_filter = ['date_input', 'status', 'name_terminal']
    search_fields = ['uuid']


@admin.register(CardInSystem)
class CardInSystemAdmin(admin.ModelAdmin):
    list_display = ['uuid', 'date_input', 'status']
    search_fields = ['uuid']
    list_filter = ['date_input', 'status', 'name_terminal']


# @admin.register(NetworkSettings)
class NetworkSettingsAdmin(admin.ModelAdmin):
    list_display = ['type_settings', 'ip', 'subnet_mask', 'gateway']
