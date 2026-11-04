import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.plasma.core as PlasmaCore

Item {
    id: compact

    required property var plasmoidItem

    readonly property var monthly: plasmoidItem.monthly

    implicitWidth: row.implicitWidth + Kirigami.Units.smallSpacing * 2
    implicitHeight: Math.max(row.implicitHeight, Kirigami.Units.iconSizes.small)

    // Le panneau dimensionne les applets via les hints du Layout attaché.
    Layout.minimumWidth: implicitWidth
    Layout.preferredWidth: implicitWidth
    Layout.maximumWidth: implicitWidth
    Layout.fillWidth: false
    Layout.minimumHeight: implicitHeight
    Layout.preferredHeight: implicitHeight
    Layout.fillHeight: false

    Row {
        id: row
        anchors.centerIn: parent
        spacing: Kirigami.Units.smallSpacing

        Rectangle {
            id: dot
            width: Kirigami.Units.smallSpacing * 1.2
            height: width
            radius: width / 2
            anchors.verticalCenter: parent.verticalCenter
            color: compact.monthly
                   ? compact.plasmoidItem.stateColor(compact.monthly.state)
                   : Kirigami.Theme.disabledTextColor
        }

        Text {
            id: label
            anchors.verticalCenter: parent.verticalCenter
            text: compact.plasmoidItem.compactText()
            color: compact.monthly
                   ? compact.plasmoidItem.stateColor(compact.monthly.state)
                   : Kirigami.Theme.textColor
            font.pointSize: Kirigami.Theme.defaultFont.pointSize
            font.weight: Font.DemiBold
        }
    }

    PlasmaCore.ToolTipArea {
        anchors.fill: parent
        active: !compact.plasmoidItem.expanded
        mainText: "OpenCode Go"
        subText: {
            var m = compact.monthly;
            if (!m)
                return compact.plasmoidItem.lastError || "Chargement…";
            return Math.round(m.percent) + " % du quota mensuel · reste "
                 + compact.plasmoidItem.fmtDuration(m.reset_in_seconds);
        }
    }

    // Plasma n'ouvre pas le popup tout seul : c'est à l'applet de le faire.
    MouseArea {
        id: clickArea
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton

        property bool wasExpanded: false

        onPressed: wasExpanded = compact.plasmoidItem.expanded
        onClicked: compact.plasmoidItem.expanded = !wasExpanded
    }
}
