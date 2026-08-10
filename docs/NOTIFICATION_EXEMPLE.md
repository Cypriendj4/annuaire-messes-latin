# Exemple de notification Telegram quotidienne

Voici le format du message envoyé chaque nuit après la mise à jour automatique.

## ✅ Résumé standard (aucune erreur)

```
🕐 Mise à jour 08/08/2026 03:01
🆕 Nouveaux : 3
✏️ Modifiés : 12
🚫 Désactivés : 1
⏱️ Durée : 42.5s

📍 Nouveaux lieux :
  • Lyon – Chapelle Saint-Irénée
  • Bordeaux – Église Saint-Augustin
  • Annecy – Chapelle Saint-François-de-Sales

✏️ Lieux modifiés :
  • Paris – Saint-Eugène (horaires)
  • Nantes – Saint-Élisabeth (célébrant)
```

## 🔴 Alerte d'erreur critique (scraping en échec)

Le workflow GitHub Actions s'arrête avec un échec visible dans l'onglet Actions.
Si le script Python échoue, une trace est envoyée dans les logs du run.

```
❌ Erreur critique : source 'amdg' en échec après 3 tentatives
Voir le run : https://github.com/TOI/REPO/actions
```

## ⚙️ Configuration

| Secret GitHub | Valeur |
|---------------|--------|
| `TELEGRAM_BOT_TOKEN` | `123456:ABC-DEF...` (via @BotFather) |
| `TELEGRAM_CHAT_ID` | `123456789` (via getUpdates) |

## 🔧 Désactiver les notifications

Supprimez les secrets `TELEGRAM_BOT_TOKEN` et `TELEGRAM_CHAT_ID` du repo, ou retirez la fonction `send_telegram()` de `update_manager.py`.
