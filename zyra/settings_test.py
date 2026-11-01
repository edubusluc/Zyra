"""Ajustes solo para ejecutar los tests (`manage.py test` los selecciona).

Parten de los ajustes normales y cambian el hash de contraseñas por uno rápido: con PBKDF2 cada
``create_user`` y cada login cuesta ~0,1-0,3 s y la suite pasaba de ~9 min a ~1,6 min. Este módulo
nunca se carga en producción (``wsgi.py``/``asgi.py`` usan ``zyra.settings``).
"""
from .settings import *  # noqa: F401,F403

PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
