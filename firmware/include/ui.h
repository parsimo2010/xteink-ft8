#pragma once
// Minimal immediate-mode renderer for the 1-bit e-paper framebuffer.
// framebuffer: 1 bit/pixel, MSB-first, bit set = white (no ink), bit clear = black.
// All drawing uses LOGICAL coordinates; when rotation != 0 each pixel is
// transposed into the landscape-native panel framebuffer at draw time.
#include <cstdint>
#include <cstddef>

class Ui {
 public:
  // rotation: 0 = none, 1 = portrait 90 deg CW, 2 = portrait 90 deg CCW.
  // Logical size must be (physW x physH) for rotation 0, else (physH x physW).
  void setTarget(uint8_t* fb, uint16_t logW, uint16_t logH,
                 uint16_t physW, uint16_t physH, int rotation) {
    _fb = fb;
    _w = logW;
    _h = logH;
    _pw = physW;
    _ph = physH;
    _rot = rotation;
    _rowBytes = physW / 8;
  }

  uint16_t width() const { return _w; }
  uint16_t height() const { return _h; }

  void clear();                                  // fill white
  void fill(uint16_t x, uint16_t y, uint16_t w, uint16_t h, bool black);
  void invert(uint16_t x, uint16_t y, uint16_t w, uint16_t h);
  void hline(uint16_t x, uint16_t y, uint16_t w, bool black);
  void vline(uint16_t x, uint16_t y, uint16_t h, bool black);
  void rect(uint16_t x, uint16_t y, uint16_t w, uint16_t h, bool black);

  // Text from the 5x7 font, upscaled to an 8x11 cell (roughly +40-57% area
  // over the old 6x8, clearly larger on the 800x480 panel).
  // Returns the number of pixels advanced.
  uint16_t text(uint16_t x, uint16_t y, const char* s, bool black);
  uint16_t textWidth(const char* s) const;

  // Large centered banner text (5x7 source drawn as 2x2 pixel blocks = 10x14).
  uint16_t textLarge(uint16_t x, uint16_t y, const char* s, bool black);
  uint16_t textLargeWidth(const char* s) const;

  static constexpr uint16_t GLYPH_W = 8;
  static constexpr uint16_t GLYPH_H = 11;
  static constexpr uint16_t ADVANCE = 10;        // glyph + 2 px spacing
  static constexpr uint16_t LARGE_W = 10;        // 5x7 as 2x2 blocks
  static constexpr uint16_t LARGE_H = 14;        // 7x2 rows
  static constexpr uint16_t LARGE_ADV = 12;      // 10 + 2 spacing

 private:
  void pixel(uint16_t x, uint16_t y, bool black);
  bool pixelRead(uint16_t x, uint16_t y) const;
  uint8_t* _fb = nullptr;
  uint16_t _w = 0, _h = 0;                       // logical
  uint16_t _pw = 0, _ph = 0, _rowBytes = 0;      // physical panel
  int _rot = 0;
};
