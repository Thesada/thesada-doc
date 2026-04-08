---
title: CYD Display Troubleshooting
parent: Testing
grand_parent: Firmware
nav_order: 5
description: "Known issues and solutions for the CYD (ESP32-2432S028R) TFT touch display board."
---

# CYD (ESP32-2432S028R) Troubleshooting

## No text on screen (fillScreen works, text doesn't)

**Cause:** TFT_eSPI font data not compiled. When using `USER_SETUP_LOADED` in build flags, ALL defaults are disabled including font compilation.

**Fix:** Add these flags to the CYD PIO environment:

```
-DLOAD_GLCD=1
-DLOAD_FONT2=1
-DLOAD_FONT4=1
-DLOAD_GFXFF=1
-DSMOOTH_FONT=1
```

Without these, `drawString()`, `print()`, and `drawChar()` silently produce no output. `fillScreen()`, `fillRect()`, `drawLine()`, and `drawPixel()` still work because they don't use font data.

## Wrong colors or garbage pixels on screen

**Cause:** Wrong ILI9341 driver variant.

**Fix:** Use `ILI9341_2_DRIVER` instead of `ILI9341_DRIVER` for CYD V2 boards (the common dual-USB variant). Also requires `invertDisplay(true)` after `init()`:

```cpp
tft.init();
tft.invertDisplay(true);
```

## Touch not responding

**Cause:** CYD V2 uses a separate SPI bus (HSPI) for the XPT2046 touch controller. TFT_eSPI's built-in touch (`tft.getTouch()`) only works when touch shares the TFT's SPI bus.

**Fix:** Use the XPT2046_Touchscreen library (MIT license) on HSPI:

```cpp
#include <XPT2046_Touchscreen.h>

SPIClass hspi(HSPI);
XPT2046_Touchscreen ts(33, 36);  // CS=33, IRQ=36

hspi.begin(25, 39, 32, 33);  // CLK, MISO, MOSI, CS
ts.begin(hspi);
ts.setRotation(3);
```

CYD touch SPI pins: CS=33, IRQ=36, CLK=25, MOSI=32, MISO=39.

## SD card init fails with "specified pins are not supported"

**Cause:** The firmware's SD module supports both `SD_MMC` (LILYGO, 4-bit mode) and `SD` (SPI mode). The CYD uses SPI-mode SD on CS=5 (shared SPI bus with TFT).

**Fix:** Set `sd.mode: "spi"` and `sd.pin_cs: 5` in config.json. The SDModule detects the mode at boot and uses the correct driver. ENABLE_SD is enabled for BOARD_CYD by default.

## OTA upload returns ok but firmware doesn't change

**Cause:** The ESP32 OTA library may silently fail on some partition configurations. The HTTP response is sent before the flash operation completes.

**Fix:** CYD uses LiteServer (`ENABLE_LITESERVER`) for OTA. Browse to the device IP, upload the .bin file via the OTA form. If that fails, flash via USB:

```bash
pio run -e esp32-cyd --target upload
pio run -e esp32-cyd --target uploadfs
```

## TFT instance: global static vs heap allocation

**Cause:** `TFT_eSPI* tft = new TFT_eSPI()` (heap-allocated) may not initialize correctly on some ESP32 variants.

**Fix:** Use a global static instance:

```cpp
static TFT_eSPI _tftInstance;
static TFT_eSPI* _tft = &_tftInstance;
```

## White flash on boot

Normal behavior. The ILI9341 powers up with a white screen before the driver initializes and sets the backlight. The splash screen appears after ~1 second.

## CYD pin reference

| Function | GPIO |
|---|---|
| TFT CS | 15 |
| TFT DC | 2 |
| TFT MOSI | 13 |
| TFT SCLK | 14 |
| TFT MISO | 12 |
| TFT backlight | 21 |
| Touch CS | 33 |
| Touch IRQ | 36 |
| Touch CLK | 25 |
| Touch MOSI | 32 |
| Touch MISO | 39 |
| SD CS | 5 |
| RGB LED R | 4 (active low) |
| RGB LED G | 16 (active low) |
| RGB LED B | 17 (active low) |
| LDR | 34 (analog) |

## Board identification

- **4-pin ribbon cable** to touch panel = resistive XPT2046 (ESP32-2432S028R)
- **6-pin ribbon cable** = capacitive GT911 (ESP32-2432S028C) - different driver needed
- **Dual USB** (micro + USB-C) = V2 board, needs `ILI9341_2_DRIVER`
