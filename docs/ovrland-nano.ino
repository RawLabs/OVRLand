// OVRLand Nano controller: joystick and Sense Rev2 telemetry over USB serial.
// Joystick module: 3V3 -> +5V pin, GND -> GND, VRX -> A0, VRY -> A1, SW -> D2.
//
// Vehicle frame (confirmed by physical tilt tests):
//   Nano +X = vehicle forward (USB connector toward front)
//   Nano -X = vehicle back
//   Nano -Y = vehicle left (driver side)
//   Nano +Y = vehicle right
//   Nano +Z = vehicle up
//   Nano -Z = vehicle down

#include <Arduino_BMI270_BMM150.h>
#include <Arduino_HS300x.h>
#include <Arduino_LPS22HB.h>
#include <Arduino_APDS9960.h>

const int JOY_X_PIN = A0;
const int JOY_Y_PIN = A1;
const int JOY_SW_PIN = 2;
const float X_CENTER = 518.0f;
const float Y_CENTER = 518.0f;

bool imu_ok = false;
bool env_ok = false;
bool baro_ok = false;
bool apds_ok = false;

float ax = 0, ay = 0, az = 0;
float gx = 0, gy = 0, gz = 0;
float mx = 0, my = 0, mz = 0;
float temp_c = 0, humidity_pct = 0;
float pressure_kpa = 0, altitude_m = 0;
int proximity = 0, color_r = 0, color_g = 0, color_b = 0, gesture = 0;

void setup() {
  pinMode(JOY_SW_PIN, INPUT_PULLUP);
  Serial.begin(115200);
  delay(1000);

  imu_ok = IMU.begin();
  env_ok = HS300x.begin();
  baro_ok = BARO.begin();
  apds_ok = APDS.begin();
}

void loop() {
  const int raw_x = analogRead(JOY_X_PIN);
  const int raw_y = analogRead(JOY_Y_PIN);
  const bool pressed = digitalRead(JOY_SW_PIN) == LOW;
  const float x_axis = constrain((raw_x - X_CENTER) / X_CENTER, -1.0f, 1.0f);
  // The installed orientation reads up as a lower raw Y value.
  const float y_axis = constrain((Y_CENTER - raw_y) / Y_CENTER, -1.0f, 1.0f);

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

  Serial.print("{\"type\":\"joystick\",\"ms\":");
  Serial.print(millis());
  Serial.print(",\"x_raw\":");
  Serial.print(raw_x);
  Serial.print(",\"y_raw\":");
  Serial.print(raw_y);
  Serial.print(",\"x\":");
  Serial.print(x_axis, 3);
  Serial.print(",\"y\":");
  Serial.print(y_axis, 3);
  Serial.print(",\"pressed\":");
  Serial.print(pressed ? "true" : "false");
  Serial.print(",\"imu_ok\":");
  Serial.print(imu_ok ? "true" : "false");
  Serial.print(",\"ax\":"); Serial.print(ax, 3);
  Serial.print(",\"ay\":"); Serial.print(ay, 3);
  Serial.print(",\"az\":"); Serial.print(az, 3);
  Serial.print(",\"gx\":"); Serial.print(gx, 3);
  Serial.print(",\"gy\":"); Serial.print(gy, 3);
  Serial.print(",\"gz\":"); Serial.print(gz, 3);
  Serial.print(",\"mx\":"); Serial.print(mx, 3);
  Serial.print(",\"my\":"); Serial.print(my, 3);
  Serial.print(",\"mz\":"); Serial.print(mz, 3);
  // Explicit vehicle-frame aliases. Values are in g and follow the mapping above.
  Serial.print(",\"forward_g\":"); Serial.print(ax, 3);
  Serial.print(",\"right_g\":"); Serial.print(ay, 3);
  Serial.print(",\"up_g\":"); Serial.print(az, 3);
  Serial.print(",\"env_ok\":");
  Serial.print(env_ok ? "true" : "false");
  Serial.print(",\"temp_c\":"); Serial.print(temp_c, 2);
  Serial.print(",\"humidity_pct\":"); Serial.print(humidity_pct, 2);
  Serial.print(",\"baro_ok\":");
  Serial.print(baro_ok ? "true" : "false");
  Serial.print(",\"pressure_kpa\":"); Serial.print(pressure_kpa, 2);
  Serial.print(",\"altitude_m\":"); Serial.print(altitude_m, 2);
  Serial.print(",\"apds_ok\":");
  Serial.print(apds_ok ? "true" : "false");
  Serial.print(",\"proximity\":"); Serial.print(proximity);
  Serial.print(",\"color_r\":"); Serial.print(color_r);
  Serial.print(",\"color_g\":"); Serial.print(color_g);
  Serial.print(",\"color_b\":"); Serial.print(color_b);
  Serial.print(",\"gesture\":"); Serial.print(gesture);
  Serial.println("}");

  delay(50); // 20 Hz; the Pi can timestamp and filter this stream.
}
