#pragma once
// Minimal immediate-mode renderer for the 1-bit e-paper framebuffer.
// framebuffer: 1 bit/pixel, MSB-first, bit set = white (no ink), bit clear = black.
#include <cstdint>
#include <cstddef>

class Ui {
 public:
  void setTarget(uint8_t* fb, uint16_t w, uint16_t h) {
    _fb = fb;
    _w = w;
    _h = h;
    _rowBytes = w / 8;
  }

  void clear();                                  // fill white
  void fill(uint16_t x, uint16_t y, uint16_t w, uint16_t h, bool black);
  void invert(uint16_t x, uint16_t y, uint16_t w, uint16_t h);
  void hline(uint16_t x, uint16_t y, uint16_t w, bool black);
  void vline(uint16_t x, uint16_t y, uint16_t h, bool black);
  void rect(uint16_t x, uint16_t y, uint16_t w, uint16_t h, bool black);

  // 5x7 text. Returns the number of pixels advanced.
  uint16_t text(uint16_t x, uint16_t y, const char* s, bool black);
  uint16_t textWidth(const char* s) const;

 private:
  void pixel(uint16_t x, uint16_t y, bool black);
  bool pixelRead(uint16_t x, uint16_t y) const;
  uint8_t* _fb = nullptr;
  uint16_t _w = 0, _h = 0, _rowBytes = 0;
};