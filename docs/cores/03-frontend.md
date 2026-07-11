# Thiết kế Kiến trúc Frontend & UI/UX (Frontend Architecture & UI/UX Design)

Tài liệu này đặc tả thiết kế giao diện (UI/UX) và kiến trúc ứng dụng phía Client (Frontend) của hệ thống.

## 1. Công nghệ Sử dụng (Frontend Stack)
- **Framework**: React.js / Vue.js / Next.js / Svelte (chọn tùy dự án).
- **Styling**: Vanilla CSS / Tailwind CSS / Styled Components.
- **State Management**: Redux Toolkit / Zustand / Pinia / React Context.
- **Build Tools**: Vite / Webpack / TurboPack.

## 2. Cấu trúc Thư mục Frontend (Directory Structure)
Cấu trúc đề xuất cho thư mục mã nguồn Frontend:

```text
📂 frontend
 ┣ 📂 src
 ┃ ┣ 📂 assets          # Hình ảnh, font chữ, icons dùng chung
 ┃ ┣ 📂 components      # Components dùng chung (Button, Modal, Input...)
 ┃ ┣ 📂 hooks           # Custom React/Vue hooks
 ┃ ┣ 📂 layouts         # Layouts trang (DefaultLayout, AdminLayout...)
 ┃ ┣ 📂 pages           # Các trang màn hình của ứng dụng
 ┃ ┣ 📂 services        # Các hàm gọi API (axios/fetch config)
 ┃ ┗ 📂 store           # Cấu hình quản lý trạng thái toàn cục (Zustand/Redux)
 ┣ 📜 index.html        # File HTML chính
 ┣ 📜 vite.config.js    # Cấu hình build Vite
 ┗ 📜 package.json      # Dependencies frontend
```

## 3. Hệ thống Thiết kế & Thẩm mỹ (Design System & Theme)
Để ứng dụng có cảm giác cao cấp (Premium UX), cần tuân thủ các nguyên tắc thiết kế sau:

- **Bảng màu (Color Palette)**:
  - Nên thiết lập bảng màu thông qua biến CSS (CSS Variables) hoặc Tailwind Theme Config.
  - Sử dụng các màu sắc tinh tế, dịu mắt (ví dụ: Slate/Zinc cho màu trung tính, Indigo/Emerald cho màu nhấn).
- **Chế độ tối (Dark Mode)**:
  - Hỗ trợ giao diện sáng/tối (Light/Dark Mode) thông qua class `.dark` ở thẻ `html`.
- **Phông chữ (Typography)**:
  - Sử dụng font chữ hiện đại, hỗ trợ đầy đủ tiếng Việt như *Inter*, *Outfit*, hoặc *Be Vietnam Pro*.
- **Hoạt ảnh (Animations)**:
  - Sử dụng micro-animations cho các nút bấm khi hover hoặc click (sử dụng thuộc tính `transition` hoặc thư viện như `framer-motion`).

## 4. Quản lý Trạng thái & API Caching
- **Trạng thái cục bộ (Local State)**: Chỉ dùng `useState` (hoặc ref) đối với các biến hiển thị trong phạm vi hẹp của Component (ví dụ: trạng thái mở/đóng Modal).
- **Trạng thái toàn cục (Global State)**: Lưu trữ thông tin đăng nhập của người dùng, cài đặt cấu hình hệ thống, giỏ hàng...
- **API Caching**: Sử dụng `@tanstack/react-query` hoặc RTK Query để quản lý cache dữ liệu từ Server, hạn chế gửi yêu cầu API lặp lại vô ích.
