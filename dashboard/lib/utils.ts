import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * 값이 실제로 쓸 수 있는 숫자인지. pandas 결측이 NaN으로 저장된 이력이 있어
 * `!= null` 검사만으로는 NaN이 통과해 화면에 "NaN%"이 찍힌다.
 */
export function isNum(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v)
}
