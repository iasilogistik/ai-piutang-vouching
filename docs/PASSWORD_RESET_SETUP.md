# Password Reset Setup

Halaman reset password tidak boleh mengarah ke `localhost` di production.

## URL production

Gunakan URL berikut untuk alur lupa password:

```text
https://ai-piutang-vouching.vercel.app/forgot-password
https://ai-piutang-vouching.vercel.app/reset-password
```

## Environment variable Vercel

Tambahkan atau pastikan nilai berikut pada Production environment:

```text
APP_BASE_URL=https://ai-piutang-vouching.vercel.app
PASSWORD_RESET_REDIRECT_URL=https://ai-piutang-vouching.vercel.app/reset-password
```

## Supabase Auth URL Configuration

Di Supabase Dashboard, buka **Authentication > URL Configuration** lalu pastikan:

```text
Site URL: https://ai-piutang-vouching.vercel.app
Redirect URLs: https://ai-piutang-vouching.vercel.app/reset-password
```

Tambahkan juga domain custom bila digunakan:

```text
https://www.voucing-piutang.com/reset-password
https://voucing-piutang.com/reset-password
```

## Catatan operasional

- Email reset password lama yang sudah terkirim bisa tetap mengarah ke `localhost`.
- Setelah konfigurasi diperbaiki, kirim ulang email dari halaman `/forgot-password`.
- Halaman `/reset-password` membaca `access_token` dari URL fragment email Supabase dan menyimpan password baru lewat endpoint `/auth/password-update`.
