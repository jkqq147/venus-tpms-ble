# venus-tpms-ble 中文说明

这个项目用于在 Victron Venus OS / GX 设备上直接显示 BLE 胎压传感器数据。

安装后，GX 本机界面会出现 `TPMS` 页面，可以扫描附近胎压传感器，并把传感器绑定到左前、右前、左后、右后四个轮位。

## 安装前准备

- Venus OS / GX 设备可以联网。
- 已经按 Victron 官方文档开启 SSH / root access。
- 插入 Venus OS 支持的 USB 蓝牙适配器。
- 胎压传感器正在广播 BLE 数据。

开启 SSH 请参考 Victron 官方文档：

[Venus OS: Root Access](https://www.victronenergy.com/live/ccgx:root_access)

## 快速安装

SSH 登录 GX 设备后，运行：

```sh
wget -O - https://raw.githubusercontent.com/jkqq147/venus-tpms-ble/master/install.sh | sh
```

安装脚本会自动下载、解压、安装并清理临时文件。安装过程中会重启 GX 图形界面，
用于加载新的 `TPMS` 菜单；不会重启整个 GX 设备。运行文件会安装到：

```text
/data/venus-tpms-ble
```

Venus OS 可以正常升级。系统升级可能替换 GX 的界面文件；升级完成后再次运行同一条
安装命令，即可恢复 `TPMS` 菜单和界面接入。

服务不绑定特定蓝牙型号或 `hci` 编号，而是使用 BlueZ 中编号最小、可扫描 BLE 的适配器。
运行中可以插拔 USB 蓝牙适配器：拔出后扫描暂停，重新出现后会自动恢复；已绑定轮位会保留
最后一次读数。

## 首次设置

1. 打开 GX 本机界面。
2. 在设备列表中打开 `TPMS`。
3. 等待 `Discovered` 列表出现胎压传感器。
4. 打开某个传感器。
5. 在 `Wheel` 中选择轮位：
   - `Front left`：左前
   - `Front right`：右前
   - `Rear left`：左后
   - `Rear right`：右后
6. 重复以上步骤，直到需要的轮位都绑定完成。

`Discovered` 列表会显示胎压、温度和 RSSI，方便判断哪个传感器更近或正在广播。

未绑定传感器是临时数据：五分钟没有再次收到广播后，会从 `Discovered` 列表移除。
已绑定的轮位会保留最后一次读数；传感器停止广播后显示为 `Stale`。

## 显示含义

设备列表中的 `TPMS` 行会按以下顺序显示四个胎压值：

```text
左前 / 右前 / 左后 / 右后
```

含义：

- `--`：未绑定传感器
- `wait`：已绑定，但本次启动后还没收到广播
- `6.17`：当前胎压，单位为 bar
- `6.17*`：旧的最后一次胎压，已经标记为 stale

进入 `TPMS` 页面后，每个轮位会显示胎压、温度和状态。打开某个轮位可以查看传感器 ID、电量、RSSI 和最后接收时间。

同一页面也会显示蓝牙状态和近期 BLE 活动。`BLE activity (5 min)` 表示最近五分钟内
实际广播过的不同 BLE 设备数量；`Manufacturer data (5 min)` 表示其中带 manufacturer
data 的设备数量。这两个数值仅用于辅助判断扫描是否有工作。如果 `Bluetooth` 不是
`Scanning`，优先检查蓝牙适配器或 BlueZ discovery。
`BLE receiver` 在收到原始广播时应显示为 `Receiving`；若接收器关闭，服务会自动重建。

## 更新

```sh
wget -O - https://raw.githubusercontent.com/jkqq147/venus-tpms-ble/master/install.sh | sh
```

## 卸载

```sh
wget -O - https://raw.githubusercontent.com/jkqq147/venus-tpms-ble/master/uninstall.sh | sh
```

## 排查

如果没有看到胎压传感器：

1. 确认 USB 蓝牙适配器已被 Venus OS 识别。
2. 确认服务状态是 `Scanning`。
3. 把胎压传感器靠近 GX 设备。
4. 等待几分钟；部分胎压传感器广播间隔较长。
5. 通过移动车辆或轻微改变胎压唤醒传感器。

查看服务状态：

```sh
dbus-send --system --print-reply \
  --dest=com.victronenergy.tpms.main \
  /StatusText \
  com.victronenergy.BusItem.GetValue
```

正常扫描时应显示：

```text
Scanning
```

如果安装后没有看到 `TPMS` 菜单，可以重启 GX UI 或重启 GX 设备。

## 说明

- 轮位绑定会持久化保存。
- 只有已绑定轮位会保存最后一次真实读数。
- 未绑定的 discovered 传感器不会在重启后保留。
- 默认不写运行日志，避免占用设备存储空间。
