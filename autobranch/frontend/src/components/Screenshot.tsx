import { useEffect, useState } from "react";

type ScreenshotProps = {
  src: string;
  alt?: string;
};

export function Screenshot({ src, alt = "节点截图" }: ScreenshotProps) {
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setFailed(false);
  }, [src]);

  if (!src) {
    return (
      <div className="screenshot screenshot--empty" role="note">
        无截图
      </div>
    );
  }

  if (failed) {
    return (
      <div className="screenshot screenshot--failed" role="note">
        截图加载失败
      </div>
    );
  }

  return <img className="screenshot" src={src} alt={alt} onError={() => setFailed(true)} />;
}