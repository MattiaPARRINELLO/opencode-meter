import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC
import org.kde.kirigami as Kirigami

QQC.Control {
    id: full

    required property var plasmoidItem

    readonly property var monthly: plasmoidItem.monthly
    readonly property var windows: plasmoidItem.usage && plasmoidItem.usage.windows
                                   ? plasmoidItem.usage.windows : ({})
    readonly property var series: plasmoidItem.usage && plasmoidItem.usage.monthly_series
                                  ? plasmoidItem.usage.monthly_series : []
    readonly property var tokens: plasmoidItem.usage && plasmoidItem.usage.tokens
                                  ? plasmoidItem.usage.tokens : []
    readonly property var stats: plasmoidItem.usage && plasmoidItem.usage.stats
                                 ? plasmoidItem.usage.stats : ({})

    property string breakdownMode: "models"

    readonly property var breakdown: {
        if (!stats.models)
            return [];
        return (breakdownMode === "projects" ? stats.projects : stats.models).slice(0, 3);
    }
    // Au moins 3 jours de relevés : avant ça, une courbe n'a rien à dire.
    readonly property bool hasSeries: {
        var days = 0;
        for (var i = 0; i < series.length; ++i) {
            if (series[i].percent > 0)
                ++days;
        }
        return days >= 3;
    }

    readonly property color trackColor: Qt.rgba(Kirigami.Theme.textColor.r,
                                               Kirigami.Theme.textColor.g,
                                               Kirigami.Theme.textColor.b, 0.16)

    implicitWidth: Kirigami.Units.gridUnit * 21
    implicitHeight: content.implicitHeight + padding * 2
    padding: Kirigami.Units.largeSpacing

    contentItem: ColumnLayout {
        id: content
        spacing: Kirigami.Units.smallSpacing

        // ---------- en-tête ----------
        RowLayout {
            Layout.fillWidth: true
            spacing: Kirigami.Units.smallSpacing
            QQC.Label {
                text: "OpenCode Go"
                font.weight: Font.DemiBold
                color: Kirigami.Theme.textColor
            }
            Item { Layout.fillWidth: true }
            QQC.Label {
                text: full.updatedText()
                font.pointSize: Kirigami.Theme.smallFont.pointSize
                color: Kirigami.Theme.disabledTextColor
            }
        }

        // ---------- quota mensuel ----------
        RowLayout {
            Layout.fillWidth: true
            spacing: Kirigami.Units.largeSpacing

            QQC.Label {
                text: full.monthly ? Math.round(full.monthly.percent) + "%" : "—"
                font.pointSize: Kirigami.Theme.defaultFont.pointSize * 3
                font.weight: Font.Bold
                color: full.monthly ? plasmoidItem.stateColor(full.monthly.state)
                                    : Kirigami.Theme.disabledTextColor
            }

            ColumnLayout {
                spacing: 0
                QQC.Label {
                    text: i18n("du quota mensuel")
                    color: Kirigami.Theme.textColor
                }
                QQC.Label {
                    text: full.monthly
                          ? i18n("reste %1", plasmoidItem.fmtDuration(full.monthly.reset_in_seconds))
                          : (plasmoidItem.lastError || i18n("Chargement…"))
                    font.pointSize: Kirigami.Theme.smallFont.pointSize
                    color: Kirigami.Theme.disabledTextColor
                }
            }
        }

        // ---------- jauge avec repère de temps écoulé ----------
        Item {
            Layout.fillWidth: true
            Layout.topMargin: Kirigami.Units.smallSpacing
            implicitHeight: Kirigami.Units.gridUnit * 0.6

            Rectangle {
                id: track
                anchors.fill: parent
                radius: height / 2
                color: full.trackColor
            }
            Rectangle {
                width: full.monthly ? Math.max(4, track.width * Math.min(full.monthly.percent / 100, 1)) : 0
                height: parent.height
                radius: height / 2
                color: full.monthly ? plasmoidItem.stateColor(full.monthly.state)
                                    : Kirigami.Theme.disabledTextColor
            }
            // repère : là où tu *devrais* être si tu suivais le rythme soutenable
            Rectangle {
                visible: !!full.monthly
                x: full.monthly ? track.width * Math.min(full.monthly.elapsed_days / full.monthly.window_days, 1) - width / 2 : 0
                width: 2
                height: parent.height * 2
                anchors.verticalCenter: parent.verticalCenter
                color: Kirigami.Theme.textColor
                opacity: 0.55
            }
        }

        // ---------- rythme ----------
        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: Kirigami.Units.smallSpacing
            spacing: Kirigami.Units.largeSpacing

            ColumnLayout {
                spacing: 0
                QQC.Label {
                    text: i18n("Ton rythme")
                    font.pointSize: Kirigami.Theme.smallFont.pointSize
                    color: Kirigami.Theme.disabledTextColor
                }
                QQC.Label {
                    text: full.monthly
                          ? full.monthly.pace_per_day.toFixed(1) + " %/j"
                          : "—"
                    font.weight: Font.DemiBold
                    color: Kirigami.Theme.textColor
                }
            }

            ColumnLayout {
                spacing: 0
                QQC.Label {
                    text: i18n("Pour tenir")
                    font.pointSize: Kirigami.Theme.smallFont.pointSize
                    color: Kirigami.Theme.disabledTextColor
                }
                QQC.Label {
                    text: full.monthly && full.monthly.sustainable_per_day !== null
                          ? full.monthly.sustainable_per_day.toFixed(1) + " %/j"
                          : "—"
                    font.weight: Font.DemiBold
                    color: Kirigami.Theme.textColor
                }
            }

            Item { Layout.fillWidth: true }

            Rectangle {
                visible: full.monthly && full.monthly.ratio !== null
                implicitWidth: ratioLabel.implicitWidth + Kirigami.Units.smallSpacing * 2
                implicitHeight: ratioLabel.implicitHeight + Kirigami.Units.smallSpacing
                radius: height / 2
                color: Qt.rgba(plasmoidItem.stateColor(full.monthly ? full.monthly.state : "ok").r,
                               plasmoidItem.stateColor(full.monthly ? full.monthly.state : "ok").g,
                               plasmoidItem.stateColor(full.monthly ? full.monthly.state : "ok").b, 0.18)
                QQC.Label {
                    id: ratioLabel
                    anchors.centerIn: parent
                    text: full.monthly && full.monthly.ratio !== null
                          ? full.monthly.ratio.toFixed(2) + "×"
                          : ""
                    font.weight: Font.DemiBold
                    color: full.monthly ? plasmoidItem.stateColor(full.monthly.state)
                                        : Kirigami.Theme.textColor
                }
            }
        }

        // ---------- projection ----------
        QQC.Label {
            Layout.fillWidth: true
            Layout.topMargin: Kirigami.Units.smallSpacing
            text: full.projectionText()
            wrapMode: Text.WordWrap
            color: full.monthly ? plasmoidItem.stateColor(full.monthly.state)
                                : Kirigami.Theme.disabledTextColor
            font.pointSize: Kirigami.Theme.smallFont.pointSize
        }

        // ---------- sparkline 14 jours ----------
        QQC.Label {
            Layout.fillWidth: true
            Layout.topMargin: Kirigami.Units.smallSpacing
            visible: !full.hasSeries
            text: i18n("Historique : se construit (3 jours de relevés)")
            font.pointSize: Kirigami.Theme.smallFont.pointSize
            color: Kirigami.Theme.disabledTextColor
            horizontalAlignment: Text.AlignHCenter
        }

        Item {
            Layout.fillWidth: true
            Layout.topMargin: Kirigami.Units.smallSpacing
            visible: full.hasSeries
            implicitHeight: Kirigami.Units.gridUnit * 2.4

            Row {
                id: spark
                anchors.fill: parent
                visible: full.hasSeries
                spacing: 2

                Repeater {
                    model: full.series
                    delegate: Item {
                        required property var modelData
                        width: (spark.width - 2 * (full.series.length - 1)) / Math.max(full.series.length, 1)
                        height: spark.height
                        Rectangle {
                            anchors.bottom: parent.bottom
                            width: parent.width
                            height: modelData.percent > 0
                                    ? Math.max(2, parent.height * Math.min(modelData.percent / 100, 1))
                                    : 0
                            radius: 1
                            color: modelData.percent >= 100
                                   ? Kirigami.Theme.negativeTextColor
                                   : Qt.rgba(Kirigami.Theme.textColor.r,
                                             Kirigami.Theme.textColor.g,
                                             Kirigami.Theme.textColor.b, 0.45)
                        }
                    }
                }
            }
        }
        QQC.Label {
            Layout.fillWidth: true
            visible: full.hasSeries
            text: i18n("Quota mensuel, 14 derniers jours")
            font.pointSize: Kirigami.Theme.smallFont.pointSize
            color: Kirigami.Theme.disabledTextColor
        }


        // ---------- où part le quota ----------
        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: Kirigami.Units.smallSpacing

            QQC.Label {
                text: i18n("Où part le quota · 30 j")
                font.pointSize: Kirigami.Theme.smallFont.pointSize
                color: Kirigami.Theme.disabledTextColor
                Layout.fillWidth: true
            }

            QQC.Button {
                text: i18n("Modèles")
                flat: true
                checkable: true
                checked: full.breakdownMode === "models"
                font.pointSize: Kirigami.Theme.smallFont.pointSize
                topPadding: 0
                bottomPadding: 0
                leftPadding: Kirigami.Units.smallSpacing
                rightPadding: Kirigami.Units.smallSpacing
                onClicked: full.breakdownMode = "models"
            }
            QQC.Button {
                text: i18n("Projets")
                flat: true
                checkable: true
                checked: full.breakdownMode === "projects"
                font.pointSize: Kirigami.Theme.smallFont.pointSize
                topPadding: 0
                bottomPadding: 0
                leftPadding: Kirigami.Units.smallSpacing
                rightPadding: Kirigami.Units.smallSpacing
                onClicked: full.breakdownMode = "projects"
            }
        }

        Repeater {
            model: full.breakdown
            delegate: RowLayout {
                required property var modelData
                Layout.fillWidth: true
                spacing: Kirigami.Units.smallSpacing

                QQC.Label {
                    text: modelData.name
                    font.pointSize: Kirigami.Theme.smallFont.pointSize
                    color: Kirigami.Theme.textColor
                    elide: Text.ElideRight
                    Layout.preferredWidth: Kirigami.Units.gridUnit * 7
                }
                Rectangle {
                    Layout.fillWidth: true
                    height: 4
                    radius: 2
                    color: full.trackColor
                    Rectangle {
                        width: parent.width * Math.min(modelData.share, 1)
                        height: parent.height
                        radius: 2
                        color: Qt.rgba(Kirigami.Theme.textColor.r,
                                       Kirigami.Theme.textColor.g,
                                       Kirigami.Theme.textColor.b, 0.55)
                    }
                }
                QQC.Label {
                    text: Math.round(modelData.share * 100) + "%"
                    font.pointSize: Kirigami.Theme.smallFont.pointSize
                    color: Kirigami.Theme.disabledTextColor
                    horizontalAlignment: Text.AlignRight
                    Layout.preferredWidth: Kirigami.Units.gridUnit * 2
                }
            }
        }

        // ---------- autres fenêtres ----------
        Rectangle {
            Layout.fillWidth: true
            Layout.topMargin: Kirigami.Units.smallSpacing
            height: 1
            color: full.trackColor
        }

        Repeater {
            model: ["rolling", "weekly"]
            delegate: RowLayout {
                required property string modelData
                Layout.fillWidth: true
                spacing: Kirigami.Units.smallSpacing

                QQC.Label {
                    text: full.windows[modelData] ? full.windows[modelData].label : ""
                    font.pointSize: Kirigami.Theme.smallFont.pointSize
                    color: Kirigami.Theme.disabledTextColor
                    Layout.preferredWidth: Kirigami.Units.gridUnit * 3.4
                }
                Rectangle {
                    Layout.fillWidth: true
                    height: 4
                    radius: 2
                    color: full.trackColor
                    Rectangle {
                        width: parent.width * Math.min((full.windows[modelData] ? full.windows[modelData].percent : 0) / 100, 1)
                        height: parent.height
                        radius: 2
                        color: full.windows[modelData]
                               ? plasmoidItem.stateColor(full.windows[modelData].state)
                               : Kirigami.Theme.disabledTextColor
                    }
                }
                QQC.Label {
                    text: full.windows[modelData]
                          ? Math.round(full.windows[modelData].percent) + "%"
                          : "—"
                    font.pointSize: Kirigami.Theme.smallFont.pointSize
                    color: Kirigami.Theme.textColor
                    Layout.preferredWidth: Kirigami.Units.gridUnit * 2
                    horizontalAlignment: Text.AlignRight
                }
            }
        }

        // ---------- pied ----------
        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: Kirigami.Units.smallSpacing

            QQC.Label {
                text: full.footerText()
                font.pointSize: Kirigami.Theme.smallFont.pointSize
                color: plasmoidItem.lastError ? Kirigami.Theme.negativeTextColor
                      : (full.stats.habit_ratio !== null && full.stats.habit_ratio > 1.3
                         ? Kirigami.Theme.neutralTextColor
                         : Kirigami.Theme.disabledTextColor)
                Layout.fillWidth: true
                elide: Text.ElideRight
            }

            QQC.Button {
                text: i18n("Rafraîchir")
                onClicked: plasmoidItem.refresh()
            }
        }
    }

    function updatedText() {
        var raw = plasmoidItem.usage ? plasmoidItem.usage.generated_at : null;
        if (!raw)
            return "";
        var d = new Date(raw);
        if (isNaN(d.getTime()))
            return "";
        return i18n("maj %1", Qt.formatTime(d, "HH:mm"));
    }

    function footerText() {
        if (plasmoidItem.lastError)
            return plasmoidItem.lastError;
        var s = full.stats;
        if (!s.today_tokens && !s.baseline_tokens)
            return "";
        var text = i18n("%1 M tokens aujourd'hui", ((s.today_tokens || 0) / 1e6).toFixed(1));
        if (s.habit_ratio !== null && s.habit_ratio !== undefined)
            text += " · " + s.habit_ratio.toFixed(1).replace(".", ",") + "× ta moyenne";
        return text;
    }

    function projectionText() {
        var m = full.monthly;
        if (!m)
            return plasmoidItem.lastError || "";
        if (m.percent >= 100)
            return i18n("Quota épuisé — reset dans %1", plasmoidItem.fmtDuration(m.reset_in_seconds));
        if (m.eta_days !== null && m.eta_days < m.remaining_days - 1)
            return i18n("Limite atteinte dans %1 j, avant le reset (dans %2 j).",
                        Math.floor(m.eta_days), Math.floor(m.remaining_days));
        if (m.projected_percent >= 100)
            return i18n("Tu frôles la limite : %1 % au reset.", Math.round(m.projected_percent));
        return i18n("À ce rythme : %1 % au reset.", Math.round(m.projected_percent));
    }
}
