// ปลายทางของลิงก์ที่เว็บส่งกลับเข้าแอปหลัง login (…/--/auth?code=…)
// ปกติ openAuthSessionAsync รับลิงก์ไปเองแล้ว — หน้านี้มีไว้กันกรณีระบบเปิดลิงก์เข้าแอปตรงๆ
// (ไม่งั้นจะเจอหน้า "ไม่พบหน้านี้") · พากลับหน้าแรกเสมอ
import { Redirect } from 'expo-router';

export default function AuthReturn() {
  return <Redirect href="/" />;
}
