import QtQuick
import org.kde.plasma.plasmoid
import org.kde.kirigami as Kirigami
import org.kde.plasma.plasma5support as P5Support

import "paths.js" as Paths

PlasmoidItem {
    id: root

    property var usage: ({})
    property bool loaded: false
    property string lastError: ""

    readonly property var monthly: usage && usage.windows && usage.windows.monthly
                                     ? usage.windows.monthly : null
    readonly property var weekly: usage && usage.windows && usage.windows.weekly
                                    ? usage.windows.weekly : null
    readonly property var rolling: usage && usage.windows && usage.windows.rolling
                                     ? usage.windows.rolling : null
    readonly property var stats: usage && usage.stats ? usage.stats : ({})

    readonly property string readCommand: "cat " + Paths.usageFile
    readonly property string refreshCommand: Paths.refreshCommand

    function stateColor(state) {
        switch (state) {
        case "over":
        case "exhausted":
            return Kirigami.Theme.negativeTextColor;
        case "warn":
            return Kirigami.Theme.neutralTextColor;
        default:
            return Kirigami.Theme.positiveTextColor;
        }
    }

    function fmtDuration(seconds) {
        if (!seconds || seconds <= 0)
            return "maintenant";
        var d = Math.floor(seconds / 86400);
        var h = Math.floor((seconds % 86400) / 3600);
        var m = Math.floor((seconds % 3600) / 60);
        if (d > 0)
            return d + " j " + h + " h";
        if (h > 0)
            return h + " h " + (m < 10 ? "0" + m : m);
        return m + " min";
    }

    function hasTodayBudget() {
        return stats.today_budget_ratio !== undefined && stats.today_budget_ratio !== null;
    }

    // État de la journée : 100 % = pile dans le budget du jour.
    function pillState() {
        if (!hasTodayBudget())
            return monthly ? monthly.state : "ok";
        var ratio = stats.today_budget_ratio;
        if (ratio >= 1.15)
            return "over";
        if (ratio >= 0.9)
            return "warn";
        return "ok";
    }

    function compactText() {
        if (hasTodayBudget())
            return Math.round(stats.today_budget_ratio * 100) + "%";
        if (!monthly)
            return "n/d";
        var days = Math.ceil(monthly.remaining_days);
        return Math.round(monthly.percent) + "% · " + days + "j";
    }

    function loadData() {
        execSource.connectSource(readCommand);
    }

    function refresh() {
        execSource.connectSource(refreshCommand);
    }

    P5Support.DataSource {
        id: execSource
        engine: "executable"
        connectedSources: []

        onNewData: function (source, data) {
            execSource.disconnectSource(source);
            var exitCode = data["exit code"];
            var stdout = data["stdout"] || "";

            if (source === root.readCommand) {
                if (exitCode !== 0 || stdout.trim() === "") {
                    root.lastError = exitCode !== 0 ? "collecteur indisponible" : "aucune donnée";
                    return;
                }
                try {
                    root.usage = JSON.parse(stdout);
                    root.loaded = true;
                    root.lastError = root.usage.ok ? "" : (root.usage.error || "erreur");
                } catch (e) {
                    root.lastError = "JSON invalide";
                }
            } else if (source === root.refreshCommand) {
                afterRefreshTimer.restart();
            }
        }
    }

    Timer {
        id: reloadTimer
        interval: 60000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: root.loadData()
    }

    // Après un refresh manuel, laisser au collecteur le temps d'écrire le JSON.
    Timer {
        id: afterRefreshTimer
        interval: 2500
        repeat: false
        onTriggered: root.loadData()
    }

    Connections {
        target: root
        function onExpandedChanged() {
            if (root.expanded)
                root.loadData();
        }
    }

    Component.onCompleted: loadData()

    compactRepresentation: CompactRepresentation {
        plasmoidItem: root
    }

    fullRepresentation: FullRepresentation {
        plasmoidItem: root
    }
}
