# OpenCode Meter

Widget KDE Plasma qui suit le **quota OpenCode Go** (fenêtres 5 h / semaine / mois)
et projette ton rythme de consommation pour t'aider à tenir jusqu'au reset.

Dans le panneau : `10% · 27j` — le pourcentage du quota mensuel et les jours restants,
colorés selon le **risque projeté** (et non le pourcentage brut). Clic → détail.

## Ce que montre le popup

- jauge du quota mensuel avec un repère de temps écoulé
- ton rythme réel (`%/jour`) face au rythme soutenable
- ratio `0.91×` : au-dessous de 1, tu tiens ; au-dessus, tu vas saturer
- projection : « à ce rythme, 92 % au reset » ou « quota épuisé dans X jours »
- courbe 14 jours (construite à partir des relevés locaux)
- fenêtres 5 h et semaine en secondaire
- tokens consommés aujourd'hui (lu dans la base OpenCode)

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

Le début de fenêtre est déduit du reset : −5 h (5 h), −7 j (semaine),
−1 mois calendaire (mois). Sous 5 h restantes, le rythme soutenable n'est pas
affiché (il tend vers l'infini).

Couleurs : vert `< 0.95×`, ambre `≥ 0.95×`, rouge `≥ 1.10×` ou quota épuisé.

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
