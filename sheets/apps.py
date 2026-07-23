from django.apps import AppConfig


class SheetsConfig(AppConfig):
    name = 'sheets'

    def ready(self):
        import sheets.signals
