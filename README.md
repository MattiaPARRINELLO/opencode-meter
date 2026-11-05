# OpenCode Meter

Widget KDE Plasma qui suit le **quota OpenCode Go** (fenêtres 5 h / semaine / mois)
et projette ton rythme de consommation pour t'aider à tenir jusqu'au reset.

Dans le panneau : `9%` — la part du **budget du jour** déjà consommée
(100 % = pile dans les temps ; plus = tu brûles plus vite que ton budget).
La couleur suit ce ratio. Clic → détail.

## Ce que montre le popup

- jauge du quota mensuel avec un repère de temps écoulé
- **aujourd'hui** : `9 % du budget` et le détail `0,3 / 3,6 % du quota`
- ton rythme réel (`%/jour`) face au rythme soutenable
- ratio `0.91×` : au-dessous de 1, tu tiens ; au-dessus, tu vas saturer
- projection : « à ce rythme, 92 % au reset » ou « quota épuisé dans X jours »
- **où part le quota** sur 30 j : bascule Modèles / Projets (part de tokens)
- **habitude du jour** : tokens consommés aujourd'hui face à ta moyenne des 7 jours
- **profil hebdomadaire** : consommation moyenne par jour (D→S), jours actifs par semaine,
  écart week-end — et la projection en tient compte
- courbe 14 jours (construite à partir des relevés locaux)
- fenêtres 5 h et semaine en secondaire

## Architecture

```
opencode-meter.timer (systemd --user, 10 min)
    └─ collect.py
         ├─ GET https://opencode.ai/zen/go/v1/usage   (quota réel)
         ├─ ~/.local/share/opencode/opencode.db      (tokens locaux, lecture seule)
         ├─ ~/.cache/opencode-meter/usage.json       (lu par le widget)
         └─ ~/.cache/opencode-meter/history.sqlite   (snapshots, courbe)
```

La clé API est lue depuis `~/.local/share/opencode/account.json` (compte `opencode-go`).
Elle n'est jamais écrite dans un log ni dans `usage.json`.

## Installation

```bash
./install.sh
```

Le script installe le collecteur dans `~/.local/lib/opencode-meter`, crée
`~/.local/bin/opencode-meter`, active le timer systemd et installe le plasmoid
(`kpackagetool6`). Il ne reste qu'à ajouter « OpenCode Meter » au panneau :
clic droit sur le panneau → *Ajouter des widgets*.

## CLI

```bash
opencode-meter            # tableau lisible
opencode-meter --json     # JSON complet
opencode-meter --notify   # idem + notification si dépassement (1×/jour)
```

## Comment la projection est calculée

| Grandeur | Formule |
|---|---|
| rythme observé | Δ% entre deux snapshots de la fenêtre courante (si ≥ 6 h d'historique) |
| rythme moyen | `% consommé ÷ jours écoulés` (début de fenêtre déduit du reset) |
| rythme soutenable | `(100 − % consommé) ÷ jours restants` |
| ratio | `rythme ÷ soutenable` |
| projection | `% consommé + rythme × jours restants` |
| habitude | `tokens du jour ÷ moyenne des 7 jours précédents` |
| profil | moyenne de tokens par jour de semaine sur 28 jours, normalisée (1 = journée moyenne) |
| projection pondérée | `% consommé ÷ jours pondérés écoulés × jours pondérés restants` |
| budget du jour | `% du quota restant ÷ jours pondérés restants × facteur du jour` |
| conso du jour | `tokens opencode-go du jour × (% consommé ÷ tokens de la fenêtre)` |
| ratio du jour | `conso du jour ÷ budget du jour` |

Le début de fenêtre est déduit du reset : −5 h (5 h), −7 j (semaine),
−1 mois calendaire (mois). Sous 5 h restantes, le rythme soutenable n'est pas
affiché (il tend vers l'infini).

Quand 14 jours de données locales existent, la projection n'est plus linéaire : chaque
jour restant est pondéré par le profil hebdomadaire (un samedi creux compte moins qu'un
mardi chargé). Le champ `projection_source` passe alors à `"habitudes"`.

Couleurs : vert `< 90 %` projeté, ambre `≥ 90 %`, rouge `≥ 100 %` ou quota épuisé.

## Limites connues

- L'API ne fournit pas d'historique : la courbe se remplit à partir du premier relevé
  (affichée après 3 jours de données).
- Le quota est en pourcentage, pas en tokens ; les tokens locaux servent d'indicateur
  d'activité, pas de conversion.
- L'endpoint `opencode.ai/zen/go/v1/usage` n'est pas documenté publiquement : si
  OpenCode le change, le widget affiche l'erreur et conserve les dernières données.

## Désinstallation

```bash
./uninstall.sh
```

Les données restent dans `~/.cache/opencode-meter` (supprime le dossier pour tout effacer).

## Licence

MIT — voir [LICENSE](LICENSE).

## Crédits

Code écrit par un assistant IA (OpenCode, DeepSeek V4.1 Flash), testé et validé
sur la machine de l'auteur.
