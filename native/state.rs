#![cfg_attr(feature = "hci-test", allow(dead_code))]

use std::{
    collections::{HashMap, HashSet},
    fs, io,
    path::PathBuf,
    time::{SystemTime, UNIX_EPOCH},
};

use serde::{Deserialize, Serialize};

pub const DISCOVERED_LIMIT: usize = 10;

#[derive(Debug, Clone, Copy, Eq, Hash, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Wheel {
    FrontLeft,
    FrontRight,
    RearLeft,
    RearRight,
}

impl Wheel {
    pub const ALL: [Wheel; 4] = [
        Wheel::FrontLeft,
        Wheel::FrontRight,
        Wheel::RearLeft,
        Wheel::RearRight,
    ];

    pub fn key(self) -> &'static str {
        match self {
            Wheel::FrontLeft => "front_left",
            Wheel::FrontRight => "front_right",
            Wheel::RearLeft => "rear_left",
            Wheel::RearRight => "rear_right",
        }
    }

    pub fn label(self) -> &'static str {
        match self {
            Wheel::FrontLeft => "Front left",
            Wheel::FrontRight => "Front right",
            Wheel::RearLeft => "Rear left",
            Wheel::RearRight => "Rear right",
        }
    }

    pub fn parse(value: &str) -> Option<Self> {
        Self::ALL.into_iter().find(|wheel| wheel.key() == value)
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Reading {
    pub sensor_id: String,
    pub name: String,
    pub pressure_bar: f64,
    pub temperature_c: f64,
    pub battery_percent: i32,
    pub alarm: i32,
    pub rssi: i32,
    pub last_seen: i64,
    pub manufacturer_data_hex: String,
}

impl Reading {
    pub fn display_name(&self) -> String {
        if self.name.starts_with("TPMS") {
            return self.name.clone();
        }
        format!(
            "TPMS_{}",
            &self.sensor_id[self.sensor_id.len().saturating_sub(6)..]
        )
    }

    pub fn core_values_equal(&self, other: &Self) -> bool {
        self.sensor_id == other.sensor_id
            && self.name == other.name
            && self.pressure_bar == other.pressure_bar
            && self.temperature_c == other.temperature_c
            && self.battery_percent == other.battery_percent
            && self.alarm == other.alarm
    }
}

#[derive(Debug, Default, Serialize, Deserialize)]
struct PersistentState {
    #[serde(default)]
    bindings: HashMap<Wheel, String>,
    #[serde(default)]
    last_readings: HashMap<Wheel, Reading>,
}

pub struct TpmsState {
    path: PathBuf,
    persistent: PersistentState,
    readings: HashMap<String, Reading>,
}

impl TpmsState {
    pub fn load(path: impl Into<PathBuf>) -> io::Result<Self> {
        let path = path.into();
        let persistent = match fs::read_to_string(&path) {
            Ok(raw) => serde_json::from_str(&raw).map_err(io::Error::other)?,
            Err(error) if error.kind() == io::ErrorKind::NotFound => PersistentState::default(),
            Err(error) => return Err(error),
        };
        Ok(Self {
            path,
            persistent,
            readings: HashMap::new(),
        })
    }

    pub fn binding(&self, wheel: Wheel) -> &str {
        self.persistent
            .bindings
            .get(&wheel)
            .map(String::as_str)
            .unwrap_or("")
    }

    pub fn assigned_wheel(&self, sensor_id: &str) -> Option<Wheel> {
        Wheel::ALL
            .into_iter()
            .find(|wheel| self.binding(*wheel) == sensor_id)
    }

    pub fn bind(&mut self, wheel: Option<Wheel>, sensor_id: &str) -> io::Result<()> {
        for candidate in Wheel::ALL {
            if self.binding(candidate) == sensor_id || Some(candidate) == wheel {
                self.persistent.bindings.insert(candidate, String::new());
            }
        }
        if let Some(wheel) = wheel {
            self.persistent.bindings.insert(wheel, sensor_id.to_owned());
            if let Some(reading) = self.readings.get(sensor_id) {
                self.persistent.last_readings.insert(wheel, reading.clone());
            }
        }
        self.save()
    }

    pub fn update(&mut self, reading: Reading) -> io::Result<()> {
        let sensor_id = reading.sensor_id.clone();
        self.readings.insert(sensor_id.clone(), reading.clone());

        let mut persist = false;
        for wheel in Wheel::ALL {
            if self.binding(wheel) == sensor_id {
                let needs_write = self
                    .persistent
                    .last_readings
                    .get(&wheel)
                    .is_none_or(|previous| !previous.core_values_equal(&reading));
                if needs_write {
                    self.persistent.last_readings.insert(wheel, reading.clone());
                    persist = true;
                }
            }
        }
        if persist {
            self.save()?;
        }
        Ok(())
    }

    pub fn checkpoint_live_readings(&mut self) -> io::Result<bool> {
        let mut changed = false;
        for wheel in Wheel::ALL {
            let sensor_id = self.binding(wheel).to_owned();
            let Some(reading) = self.readings.get(&sensor_id) else {
                continue;
            };
            let needs_write = self
                .persistent
                .last_readings
                .get(&wheel)
                .is_none_or(|previous| previous.last_seen != reading.last_seen);
            if needs_write {
                self.persistent.last_readings.insert(wheel, reading.clone());
                changed = true;
            }
        }
        if changed {
            self.save()?;
        }
        Ok(changed)
    }

    pub fn prune_expired_unbound(&mut self, now: i64, max_age_seconds: i64) -> bool {
        let bound = Wheel::ALL
            .into_iter()
            .map(|wheel| self.binding(wheel).to_owned())
            .filter(|sensor_id| !sensor_id.is_empty())
            .collect::<HashSet<_>>();
        let before = self.readings.len();
        self.readings.retain(|sensor_id, reading| {
            bound.contains(sensor_id) || now - reading.last_seen <= max_age_seconds
        });
        self.readings.len() != before
    }

    pub fn discovered(&self) -> Vec<&Reading> {
        let bound = Wheel::ALL
            .into_iter()
            .map(|wheel| self.binding(wheel))
            .filter(|sensor_id| !sensor_id.is_empty())
            .collect::<HashSet<_>>();
        let mut readings = self.readings.values().collect::<Vec<_>>();
        readings.sort_by_key(|reading| (reading.rssi, reading.last_seen));
        readings.reverse();

        let mut selected = readings
            .iter()
            .copied()
            .take(DISCOVERED_LIMIT)
            .collect::<Vec<_>>();
        for reading in readings {
            if !bound.contains(reading.sensor_id.as_str())
                || selected
                    .iter()
                    .any(|item| item.sensor_id == reading.sensor_id)
            {
                continue;
            }
            if selected.len() < DISCOVERED_LIMIT {
                selected.push(reading);
            } else if let Some(index) = selected
                .iter()
                .rposition(|item| !bound.contains(item.sensor_id.as_str()))
            {
                selected[index] = reading;
            }
        }
        selected.sort_by_key(|reading| (reading.rssi, reading.last_seen));
        selected.reverse();
        selected
    }

    pub fn reading_for_wheel(&self, wheel: Wheel) -> Option<(&Reading, bool)> {
        let sensor_id = self.binding(wheel);
        if sensor_id.is_empty() {
            return None;
        }
        if let Some(reading) = self.readings.get(sensor_id) {
            return Some((reading, false));
        }
        self.persistent
            .last_readings
            .get(&wheel)
            .filter(|reading| reading.sensor_id == sensor_id)
            .map(|reading| (reading, true))
    }

    fn save(&self) -> io::Result<()> {
        if let Some(parent) = self.path.parent() {
            fs::create_dir_all(parent)?;
        }
        let temporary = self.path.with_extension("json.tmp");
        let encoded = serde_json::to_vec(&self.persistent).map_err(io::Error::other)?;
        fs::write(&temporary, encoded)?;
        fs::rename(temporary, &self.path)
    }
}

pub fn unix_time() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs() as i64
}

#[cfg(test)]
mod tests {
    use super::{Reading, TpmsState, Wheel};

    fn reading(id: &str, rssi: i32) -> Reading {
        Reading {
            sensor_id: id.to_owned(),
            name: String::new(),
            pressure_bar: 6.1,
            temperature_c: 30.0,
            battery_percent: 100,
            alarm: 0,
            rssi,
            last_seen: 1,
            manufacturer_data_hex: String::new(),
        }
    }

    #[test]
    fn binding_is_unique_across_wheels_and_sensors() {
        let directory = tempfile::tempdir().unwrap();
        let mut state = TpmsState::load(directory.path().join("state.json")).unwrap();
        state.update(reading("A", -70)).unwrap();
        state.bind(Some(Wheel::FrontLeft), "A").unwrap();
        state.bind(Some(Wheel::RearRight), "A").unwrap();
        assert_eq!(state.binding(Wheel::FrontLeft), "");
        assert_eq!(state.binding(Wheel::RearRight), "A");
    }

    #[test]
    fn discovered_is_limited_and_sorted_by_signal() {
        let directory = tempfile::tempdir().unwrap();
        let mut state = TpmsState::load(directory.path().join("state.json")).unwrap();
        for index in 0..12 {
            state
                .update(reading(&format!("S{index}"), -100 + index))
                .unwrap();
        }
        let discovered = state.discovered();
        assert_eq!(discovered.len(), 10);
        assert_eq!(discovered[0].sensor_id, "S11");
    }

    #[test]
    fn checkpoint_persists_new_timestamp_without_value_change() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("state.json");
        let mut state = TpmsState::load(&path).unwrap();
        state.bind(Some(Wheel::FrontLeft), "sensor").unwrap();

        let first = reading("sensor", -70);
        state.update(first).unwrap();
        let mut second = reading("sensor", -70);
        second.last_seen = 61;
        state.update(second).unwrap();

        let before = TpmsState::load(&path).unwrap();
        assert_eq!(
            before
                .reading_for_wheel(Wheel::FrontLeft)
                .unwrap()
                .0
                .last_seen,
            1
        );

        assert!(state.checkpoint_live_readings().unwrap());
        let after = TpmsState::load(&path).unwrap();
        assert_eq!(
            after
                .reading_for_wheel(Wheel::FrontLeft)
                .unwrap()
                .0
                .last_seen,
            61
        );
    }

    #[test]
    fn pruning_keeps_bound_sensor_only() {
        let directory = tempfile::tempdir().unwrap();
        let mut state = TpmsState::load(directory.path().join("state.json")).unwrap();
        state.update(reading("bound", -80)).unwrap();
        state.update(reading("unbound", -60)).unwrap();
        state.bind(Some(Wheel::FrontLeft), "bound").unwrap();

        assert!(state.prune_expired_unbound(400, 300));
        let sensors = state
            .discovered()
            .into_iter()
            .map(|reading| reading.sensor_id.as_str())
            .collect::<Vec<_>>();
        assert_eq!(sensors, vec!["bound"]);
    }
}
