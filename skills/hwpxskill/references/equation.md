# 한글 수식 스크립트 요약

한글 수식 편집기의 스크립트(수식 스크립트 6.0)만 쓴다. **LaTeX는 넣지 않는다.**
아래 꼴은 실제 한글 문서의 수식 2만여 개에서 쓰이고, 미리보기 엔진(rhwp)에서도 그려지는 것들이다.

- 글 속: `"값은 <eq>{1} over {2}</eq>이다"` — 주변 글자 크기에 맞춰 글자처럼 들어간다.
- 따로 한 줄: `"<eq block>int _{0} ^{1} x ^{2} dx = {1} over {3}</eq>"` — 가운데 정렬한 문단.
- 넣기 전에 검사: `hwpx equation check "스크립트" ["스크립트" …]` (오류는 저장 전에 막히고, 경고는 더 나은 꼴을 알려 준다).

## 기본 규칙

| 규칙 | 예 |
|---|---|
| 묶음은 `{ }` | `{a+b} over {2}` |
| 띄어쓰기로 명령을 가른다 | `sin x`, `alpha + beta` |
| 보이는 빈칸: `~`(보통), `` ` ``(1/4) | `f(x) ~=~ 0`, ``f` `(x)`` |
| 글자 그대로: 큰따옴표 | `3 "cm"`, `"(단, " x>0 ")"` |
| 곧은 글자: `rm`, 기울인 글자: `it`, 굵게: `bold` | `rm P(A)`, `rm {kg}`, `rm AB` (선분 이름) |
| 명령은 대소문자 무관(`times`=`TIMES`), **그리스 문자·화살표는 구분** | `alpha`(α) `Alpha`(Α), `rarrow`(→) `RARROW`(⇒) |

## 자주 쓰는 꼴

| 뜻 | 스크립트 | LaTeX였다면 |
|---|---|---|
| 분수 | `{a} over {b}` | `\frac{a}{b}` |
| 위·아래 첨자 | `x^2`, `a_n`, `x_{i}^{2}`, `e^{-x}` | 같음 |
| 제곱근·n제곱근 | `sqrt {x}`, `root {3} of {x}` | `\sqrt{x}`, `\sqrt[3]{x}` |
| 괄호 크기 자동 | `LEFT ( {1} over {2} RIGHT )`, `left [ x right ]`, `left lbrace x right rbrace` | `\left( … \right)` |
| 합·곱 | `sum _{k=1} ^{n} a_k`, `prod _{k=1} ^{n} k` | `\sum_{k=1}^{n}` |
| 적분 | `int _{0} ^{1} f(x) dx`, `dint`, `oint` | `\int_0^1` |
| 극한 | `lim _{x -> 0} {sin x} over {x}`, `lim _{n -> inf} a_n` | `\lim_{x\to0}` |
| 로그·삼각함수 | `log _{2} 8`, `ln x`, `sin ^{2} x + cos ^{2} x = 1` | `\log_2 8` |
| 조합·순열 | `{}_{n} rm C _{r}`, `{}_{5} rm P _{2}` | `{}_nC_r` |
| 연립·경우 | `cases{x & (x ge 0) # -x & (x < 0)}` | `\begin{cases}` |
| 행렬 | `pmatrix{a & b # c & d}` 소괄호, `bmatrix{…}` 대괄호, `dmatrix{…}` 행렬식 | `\begin{pmatrix}` |
| 여러 줄 맞춤 | `eqalign{f(x) & = x^2 + 1 # & = 5}`, `pile{a # b}` (`lpile`, `rpile`) | `align` |

`&`는 칸 나눔, `#`은 줄 나눔 (행렬·`cases`·`pile`·`eqalign` 안에서만).

절댓값처럼 세로 막대 괄호는 `left | x right |` (크기 자동) 또는 그냥 `|x|`.

## 기호

| 기호 | 스크립트 | 기호 | 스크립트 |
|---|---|---|---|
| × ÷ · | `times` `div` `cdot` | ± ∓ | `pm` `mp` |
| ≤ ≥ | `le` `ge` (또는 `LEQ` `GEQ`) | ≠ | `!=` 또는 `ne` |
| ≈ ≡ ∼ ≅ ∝ | `approx` `equiv` `sim` `cong` `propto` | ∞ | `inf` |
| → ← ↔ | `->` 또는 `rarrow`, `larrow`, `lrarrow` | ⇒ ⇔ | `RARROW` `LRARROW` |
| ∈ ∉ ⊂ ⊆ ⊃ | `in` `notin` `subset` `subseteq` `supset` | ∪ ∩ ∅ | `cup` `cap` `emptyset` |
| ∴ ∵ ∀ ∃ | `therefore` `because` `forall` `exist` | ∂ ∇ | `partial` `nabla` |
| ∠ △ ⊥ ° | `angle` `triangle` `bot` `DEG` | ′ (프라임) | `prime` 또는 `'` (`f'(x)`) |
| ⋯ … ⋮ ⋱ | `cdots` `ldots` `vdots` `ddots` | 세로 막대(조건부 확률) | `vert` (`rm P LEFT ( A vert B RIGHT )`) |

그리스 문자: `alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi rho sigma tau upsilon phi chi psi omega`, 대문자는 **첫 글자만 대문자** `Gamma Delta Theta Lambda Pi Sigma Phi Psi Omega`.

## 장식 (위·아래 표시)

| 모양 | 스크립트 |
|---|---|
| 선분 AB (윗줄) | `rm bar {AB}` |
| 벡터 | `vec {a}`, `rm vec {AB}` |
| 호 AB | `rm arch {AB}` |
| 평균 x̄ | `bar {x}` |
| 모자·물결·점 | `hat {x}`, `tilde {x}`, `dot {x}`, `ddot {x}` |
| 밑줄 | `under {x}` |
| 사선(부정) | `not =` |

## 교과 예시

| 내용 | 스크립트 |
|---|---|
| 근의 공식 | `x = {-b pm sqrt {b^2 - 4ac}} over {2a}` |
| 이차방정식 | `x^2 - 5x + 6 = 0` |
| 삼각형 넓이 | `S = {1} over {2} ab sin C` |
| 등차수열 합 | `S_n = {n(a_1 + a_n)} over {2}` |
| 시그마 | `sum _{k=1} ^{n} k^2 = {n(n+1)(2n+1)} over {6}` |
| 정적분 | `int _{0} ^{2} (3x^2 + 1) dx = 10` |
| 미분계수 | `f'(a) = lim _{h -> 0} {f(a+h) - f(a)} over {h}` |
| 확률 | `rm P(A cup B) = rm P(A) + rm P(B) - rm P(A cap B)` |
| 각의 크기 | `angle rm ABC = 90 DEG` |
| 선분 길이 | `rm bar {AB} = 2 sqrt {3}` |
| 구간 | `-3 le x < 1` |

- 절댓값: `left | x - 3 right | < 2`
- 벡터 내적: `rm vec {a} cdot rm vec {b} = left | rm vec {a} right | left | rm vec {b} right | cos theta`

## 한글이 스스로 떼어 읽는 경우

한글은 붙여 쓴 낱말도 앞에서부터 명령을 떼어 읽는다: `sinx` = `sin x`, `overa` = `over a`, `rmAB` = `rm AB`, `tantheta` = `tan theta`. 기존 문서에는 이런 꼴이 많지만 **새로 쓸 때는 띄어 쓴다.** 반대로 변수 이름이 명령으로 시작하면 명령으로 읽히니(`int`eger, `in`dex) 글자는 따옴표로 감싼다.

## 피할 것 (검사기가 경고)

| 쓰지 말 것 | 대신 |
|---|---|
| `\frac`, `\sqrt`, `$…$` 등 LaTeX | 위 표의 한글 꼴 (오류로 막힘) |
| `sum from {k=1} to {n}`, `lim from {…}` | `sum _{k=1} ^{n}`, `lim _{x -> 0}` |
| `<=` `>=` `=>` `<=>` `+-` | `le` `ge` `RARROW` `LRARROW` `pm` |
| `DELTA`, `SIGMA` (모두 대문자) | `Delta`, `Sigma` |
| `x sub 1` | `x_1` |

## 기존 수식 읽기·고치기

```bash
hwpx equation list 문서.hwpx                     # #번호 @위치: 스크립트
hwpx equation set 문서.hwpx --index 3 --script "{a} over {b}" -o 결과.hwpx
hwpx equation set 문서.hwpx --find "x^2+1" --script "x^3" -o 결과.hwpx   # 스크립트 일부로 찾기
```
여러 개를 한 번에 바꾸려면 `fill`의 `"equations": {"3": "…", "x^2+1": "…"}`. 크기(hp:sz)는 새 스크립트로 다시 추정하고, 한글은 열 때 정확히 다시 그린다.
