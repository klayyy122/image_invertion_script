# 🎨 Image Ivertor script

[![C++](https://img.shields.io/badge/C++-17-blue.svg)](https://en.cppreference.com/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Multi-threaded](https://img.shields.io/badge/multi--threaded-✔-success.svg)]()

**High-performance image color inverter with multi-threading support** - processes thousands of images in parallel with a choice of operating modes.

## ✨ Features
- 📊 **Statistics of efficiency** 
- 📁 **Support formats**: JPG, PNG, JPEG

## 📦 Installation & build

### Requerments
-  C++17 (g++ 7.4+ / clang++ 6.0+)
- Library STB Image (already included)

### build
```bash
# clone repo
git clone https://github.com/yourusername/image_invertion_script.git
cd image_invertion_script

# build
g++ -std=c++17 main.cpp -o main
