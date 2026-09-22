// OVRLand Nano controller: Sense Rev2 telemetry over USB serial and BLE.
// Joystick module: 3V3 -> +5V pin, GND -> GND, VRX -> A0, VRY -> A1, SW -> D2.
// Vehicle frame: +X forward, +Y right, +Z up.

#include <Arduino_BMI270_BMM150.h>
#include <Arduino_HS300x.h>
#include <Arduino_LPS22HB.h>
#include <Arduino_APDS9960.h>
#include <ArduinoBLE.h>

const int JOY_X_PIN = A0;
const int JOY_Y_PIN = A1;
const int JOY_SW_PIN = 2;
const float X_CENTER = 518.0f;
const float Y_CENTER = 518.0f;

// GATT contract: a JSON record is split into notification packets no larger
// than 20 bytes. Packet header: flags, frame sequence, packet sequence, data
// length. START begins a record and END finishes it. A dropped packet drops
// only that record; the next START resynchronizes the Pi reader.
const char *BLE_SERVICE_UUID = "0f0c48e7-9d3f-4c79-90d6-1e664d2cba00";
const char *BLE_TELEMETRY_UUID = "0f0c48e7-9d3f-4c79-90d6-1e664d2cba01";
const uint8_t BLE_PACKET_BYTES = 20;
const uint8_t BLE_HEADER_BYTES = 4;
const uint8_t BLE_PAYLOAD_BYTES = BLE_PACKET_BYTES - BLE_HEADER_BYTES;
const uint8_t BLE_START = 0x01;
const uint8_t BLE_END = 0x02;
const unsigned long BLE_PERIOD_MS = 750;

BLEService telemetryService(BLE_SERVICE_UUID);
BLECharacteristic telemetryCharacteristic(BLE_TELEMETRY_UUID, BLERead | BLEIndicate,
                                           BLE_PACKET_BYTES);

class BlePacketWriter : public Print {
 public:
  void begin(uint8_t frame) {
    frame_ = frame;
    packet_ = 0;
    used_ = 0;
    first_ = true;
  }

  size_t write(uint8_t byte) override {
    buffer_[BLE_HEADER_BYTES + used_++] = byte;
    if (used_ == BLE_PAYLOAD_BYTES) sendData();
    return 1;
  }

  void finish() {
    if (used_) sendData();
    uint8_t end[] = {BLE_END, frame_, packet_, 0};
    telemetryCharacteristic.writeValue(end, sizeof(end));
    BLE.poll();
  }

 private:
  void sendData() {
    buffer_[0] = first_ ? BLE_START : 0;
    buffer_[1] = frame_;
    buffer_[2] = packet_++;
    buffer_[3] = used_;
    telemetryCharacteristic.writeValue(buffer_, BLE_HEADER_BYTES + used_);
    BLE.poll();
    used_ = 0;
    first_ = false;
  }

  uint8_t buffer_[BLE_PACKET_BYTES];
  uint8_t frame_ = 0;
  uint8_t packet_ = 0;
  uint8_t used_ = 0;
  bool first_ = true;
};

bool imu_ok = false;
bool env_ok = false;
bool baro_ok = false;
bool apds_ok = false;
bool ble_ok = false;

float ax = 0, ay = 0, az = 0;
float gx = 0, gy = 0, gz = 0;
float mx = 0, my = 0, mz = 0;
float temp_c = 0, humidity_pct = 0;
float pressure_kpa = 0, altitude_m = 0;
int proximity = 0, color_r = 0, color_g = 0, color_b = 0, gesture = 0;
unsigned long last_ble_ms = 0;
uint8_t ble_frame = 0;

void readSensors() {
  if (imu_ok) {
    if (IMU.accelerationAvailable()) IMU.readAcceleration(ax, ay, az);
    if (IMU.gyroscopeAvailable()) IMU.readGyroscope(gx, gy, gz);
    if (IMU.magneticFieldAvailable()) IMU.readMagneticField(mx, my, mz);
  }
  if (env_ok) {
    temp_c = HS300x.readTemperature();
    humidity_pct = HS300x.readHumidity();
  }
  if (baro_ok) {
    pressure_kpa = BARO.readPressure();
    altitude_m = BARO.readAltitude();
  }
  if (apds_ok) {
    if (APDS.proximityAvailable()) proximity = APDS.readProximity();
    if (APDS.colorAvailable()) APDS.readColor(color_r, color_g, color_b);
    if (APDS.gestureAvailable()) gesture = APDS.readGesture();
  }
}

void writeTelemetry(Print &out, int raw_x, int raw_y, float x_axis, float y_axis,
                    bool pressed) {
  out.print("{\"type\":\"joystick\",\"ms\":"); out.print(millis());
  out.print(",\"x_raw\":"); out.print(raw_x);
  out.print(",\"y_raw\":"); out.print(raw_y);
  out.print(",\"x\":"); out.print(x_axis, 3);
  out.print(",\"y\":"); out.print(y_axis, 3);
  out.print(",\"pressed\":"); out.print(pressed ? "true" : "false");
  out.print(",\"imu_ok\":"); out.print(imu_ok ? "true" : "false");
  out.print(",\"ax\":"); out.print(ax, 3); out.print(",\"ay\":"); out.print(ay, 3);
  out.print(",\"az\":"); out.print(az, 3); out.print(",\"gx\":"); out.print(gx, 3);
  out.print(",\"gy\":"); out.print(gy, 3); out.print(",\"gz\":"); out.print(gz, 3);
  out.print(",\"mx\":"); out.print(mx, 3); out.print(",\"my\":"); out.print(my, 3);
  out.print(",\"mz\":"); out.print(mz, 3);
  out.print(",\"forward_g\":"); out.print(ax, 3);
  out.print(",\"right_g\":"); out.print(ay, 3);
  out.print(",\"up_g\":"); out.print(az, 3);
  out.print(",\"env_ok\":"); out.print(env_ok ? "true" : "false");
  out.print(",\"temp_c\":"); out.print(temp_c, 2);
  out.print(",\"humidity_pct\":"); out.print(humidity_pct, 2);
  out.print(",\"baro_ok\":"); out.print(baro_ok ? "true" : "false");
  out.print(",\"pressure_kpa\":"); out.print(pressure_kpa, 2);
  out.print(",\"altitude_m\":"); out.print(altitude_m, 2);
  out.print(",\"apds_ok\":"); out.print(apds_ok ? "true" : "false");
  out.print(",\"proximity\":"); out.print(proximity);
  out.print(",\"color_r\":"); out.print(color_r); out.print(",\"color_g\":"); out.print(color_g);
  out.print(",\"color_b\":"); out.print(color_b); out.print(",\"gesture\":"); out.print(gesture);
  out.println("}");
}

// BLE uses compact integer JSON so a complete sample is only about seven
// acknowledged packets. The Pi expands these fields to the normal telemetry
// schema; USB keeps the verbose, human-readable stream above.
void writeBleTelemetry(Print &out, float x_axis, float y_axis, bool pressed) {
  uint8_t flags = (imu_ok ? 1 : 0) | (env_ok ? 2 : 0) | (baro_ok ? 4 : 0) |
                  (apds_ok ? 8 : 0);
  out.print("{\"m\":"); out.print(millis());
  out.print(",\"x\":"); out.print((int)(x_axis * 100));
  out.print(",\"y\":"); out.print((int)(y_axis * 100));
  out.print(",\"b\":"); out.print(pressed ? 1 : 0);
  out.print(",\"f\":"); out.print(flags);
  out.print(",\"a\":["); out.print((int)(ax * 1000)); out.print(',');
  out.print((int)(ay * 1000)); out.print(','); out.print((int)(az * 1000));
  out.print("],\"e\":["); out.print((int)(temp_c * 100)); out.print(',');
  out.print((int)humidity_pct); out.print(','); out.print((int)(pressure_kpa * 10));
  out.print(','); out.print((int)(altitude_m * 10));
  out.print("],\"l\":["); out.print(color_r); out.print(','); out.print(color_g);
  out.print(','); out.print(color_b); out.print(','); out.print(proximity); out.println("]}");
}

void setup() {
  pinMode(JOY_SW_PIN, INPUT_PULLUP);
  Serial.begin(115200);
  delay(1000);
  imu_ok = IMU.begin();
  env_ok = HS300x.begin();
  baro_ok = BARO.begin();
  apds_ok = APDS.begin();

  ble_ok = BLE.begin();
  if (ble_ok) {
    BLE.setLocalName("OVRLand Nano");
    BLE.setAdvertisedService(telemetryService);
    telemetryService.addCharacteristic(telemetryCharacteristic);
    BLE.addService(telemetryService);
    BLE.advertise();
  }
}

void loop() {
  const int raw_x = analogRead(JOY_X_PIN);
  const int raw_y = analogRead(JOY_Y_PIN);
  const bool pressed = digitalRead(JOY_SW_PIN) == LOW;
  const float x_axis = constrain((raw_x - X_CENTER) / X_CENTER, -1.0f, 1.0f);
  const float y_axis = constrain((Y_CENTER - raw_y) / Y_CENTER, -1.0f, 1.0f);
  readSensors();
  writeTelemetry(Serial, raw_x, raw_y, x_axis, y_axis, pressed);

  if (ble_ok) {
    BLE.poll();
    const unsigned long now = millis();
    if (now - last_ble_ms >= BLE_PERIOD_MS) {
      BlePacketWriter writer;
      writer.begin(ble_frame++);
      writeBleTelemetry(writer, x_axis, y_axis, pressed);
      writer.finish();
      last_ble_ms = now;
    }
  }
  delay(50);
}
