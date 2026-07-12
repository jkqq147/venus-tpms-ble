import QtQuick 1.1
import com.victron.velib 1.0

MbPage {
	title: qsTr("Diagnostics")

	model: VisibleItemModel {
		MbItemValue {
			description: qsTr("Status")
			item.bind: "com.victronenergy.tpms.main/StatusText"
		}

		MbItemValue {
			description: qsTr("Bluetooth")
			item.bind: "com.victronenergy.tpms.main/Bluetooth/StatusText"
		}

		MbItemValue {
			description: qsTr("BLE receiver")
			item.bind: "com.victronenergy.tpms.main/Bluetooth/ReceiverStatus"
		}

		MbItemValue {
			description: qsTr("BLE activity (60 sec)")
			item.bind: "com.victronenergy.tpms.main/Bluetooth/DeviceCount"
		}

		MbItemValue {
			description: qsTr("Manufacturer data (60 sec)")
			item.bind: "com.victronenergy.tpms.main/Bluetooth/ManufacturerDataCount"
		}
	}
}
