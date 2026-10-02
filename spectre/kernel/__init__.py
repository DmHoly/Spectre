"""Le noyau de Spectre : ce que tous les plugins partagent sans qu'aucun ne soit une fonctionnalité
métier - base SQLite et migrations, manifeste d'un plugin, erreurs, verrous, e-mail, service des
pages et construction de l'application (voir ``ARCHITECTURE.md`` § 2). Aucun module d'ici n'importe
un plugin : seule :func:`spectre.kernel.app.create_app` lit la liste ``spectre.plugins.PLUGINS``
quand on ne lui en passe pas.
"""
