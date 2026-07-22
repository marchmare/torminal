import i18n
import os
import pathlib
import locale

path = pathlib.Path(os.path.abspath(__file__)).parent / "resources" / "translations"
i18n.load_path.append(path)
langcode, encoding = locale.getlocale()
i18n.set("locale", langcode)
i18n.set("fallback", "en_US")
i18n.set("filename_format", "{locale}.{format}")
