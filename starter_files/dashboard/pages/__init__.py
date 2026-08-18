"""Pages — jedna zakladka = jeden plik.

Kazdy modul eksportuje jedna funkcje `page_<nazwa>()` ktora renderuje
zakladke. Konwencja: importy tylko z `dashboard.queries` + `dashboard.callbacks`
+ `dashboard.helpers` + `dashboard.constants` + `dashboard.utils`. Zaden
raw SQL w pages.
"""
