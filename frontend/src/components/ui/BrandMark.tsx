interface BrandMarkProps {
  size?: number
}

export function BrandMark({ size = 22 }: BrandMarkProps) {
  return (
    <span
      className="brand-mark"
      style={{ width: size, height: size }}
    />
  )
}
