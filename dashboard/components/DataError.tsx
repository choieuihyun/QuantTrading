"use client";
import { AlertTriangle } from "lucide-react";

/**
 * Firestore 읽기 실패를 '데이터 없음'과 구분해 보여준다.
 * 새 컬렉션을 추가하면 보안 규칙에 읽기 권한을 열어줘야 하는데,
 * 그걸 빠뜨리면 permission-denied가 나면서 화면상으로는 빈 것과 똑같아 보인다.
 */
export function DataError({ err, collection }: { err: unknown; collection: string }) {
  const msg = err instanceof Error ? err.message : String(err);
  const denied = /permission|insufficient/i.test(msg);

  return (
    <div className="bg-rose-500/5 border border-rose-500/25 rounded-2xl px-5 py-6">
      <div className="flex items-center gap-2 text-rose-300 font-medium">
        <AlertTriangle size={16} />
        데이터를 읽지 못했습니다
      </div>

      {denied ? (
        <div className="mt-3 space-y-2 text-sm text-white/60">
          <p>
            <code className="text-rose-200/80">{collection}</code> 컬렉션에 읽기 권한이 없습니다.
            데이터는 저장돼 있지만 브라우저가 접근하지 못하는 상태입니다.
          </p>
          <p className="text-white/40 text-xs">
            Firebase 콘솔 → Firestore → 규칙에서 이 컬렉션의 읽기를 허용해야 합니다.
          </p>
          <pre className="text-xs bg-black/40 border border-white/10 rounded-lg p-3 overflow-x-auto text-white/70">
{`match /${collection}/{doc} {
  allow read: if true;
}`}
          </pre>
        </div>
      ) : (
        <p className="mt-3 text-sm text-white/50 break-all">{msg}</p>
      )}
    </div>
  );
}
