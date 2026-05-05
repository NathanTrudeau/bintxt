# bintxt Examples

Three self-contained example projects. Each has its own `bintxt_cfg.yaml` and `configs/` directory.
Copy `bintxt.sh` next to the YAML to run any of them.

---

## `basic_8bit/`

**Format:** 8-bit words · 6 per line · little-endian · 32-bit addresses

Simple microcontroller register maps — LED driver config and sensor calibration tables.
Both files are `.txt` sources. Running bintxt.sh will pack them to `.bin` and verify.

| File | Description |
|------|-------------|
| `configs/led_config.txt` | LED driver: control, PWM, blink timers, fault flags |
| `configs/sensor_cal.txt` | Sensor calibration: temp, pressure, humidity, accelerometer |

---

## `wide_words/`

**Format:** 32-bit words · 4 per line · little-endian · SHA-256 checksums

ARM/RISC-V style tables — DMA channel descriptors and an RTOS task scheduler table.
Both files are `.txt` sources; each row is one logical entry.

| File | Description |
|------|-------------|
| `configs/dma_cfg.txt` | 4-channel DMA descriptor table + control block |
| `configs/task_sched.txt` | RTOS 5-task schedule: stack ptr, priority, period, flags |

---

## `soc_bin_files/`

**Format:** Mixed — five different format profiles (see table)

Pre-built SoC binaries ready to unpack. Running bintxt.sh will unpack each `.bin` to a labeled
`.txt` so you can inspect and edit the register values, then re-pack and verify.

| File | Word | WPL | Endian | Checksum | Description |
|------|------|-----|--------|----------|-------------|
| `configs/boot_cfg.bin` | 32-bit | 4 | LE | CRC32 | Boot ROM: magic, version, clocks, memory map, canary |
| `configs/gpio_map.bin` | 8-bit | 8 | LE | CRC32 | GPIO pin config — one byte per pin, 4 ports × 8 pins |
| `configs/periph_ctrl.bin` | 16-bit | 2 | LE | MD5 | SPI / I2C / UART / Timer peripheral control registers |
| `configs/irq_table.bin` | 32-bit | 4 | LE | CRC32 | ARM interrupt vector table — 16 handler addresses |
| `configs/nvmem.bin` | 8-bit | 2 | **BE** | SHA-256 | Factory NV memory: device ID, calibration, serial number |
