<!--
오늘 진행할 톡의 구조를 만들고자 해. 내가 너에게 주는 프롬프트도 여기에 일단 기록해주고 (내가 너에게 주는 프롬프트는 마크다운에서 comment 형태로 기록해줘!)

(일단 로컬에서 너와 같이 1차적인 작업을 한 뒤에, 나에 대한 배경 지식을 좀더 가지고 있는 Claude와 함께 좀더 구체화한 후 정리를 할 거야.

일단 오늘 진행할 톡은 내가 했던 내용을 발표하기보다는, 우리가 함께 진행할 일이 어떤 모양새를 가졌으면 하는지, 어떤 것이 가능할 지 알아보는 측면의 톡이면 좋을 것 같아. 뭐랄까 일반적인 research 여러개를 summary하는 형태의 seminar라기보다는, 디스커션을 촉진시키기 위해 몇 가지 포인터들을 제공하는 것을 목적으로 하는 톡이었으면 좋겠어.

와중에 앞 장에는 간단하게 내 소개를 하고 넘어가고 싶다. 내가 누구인지는 claude가 좀더 잘 알테니 디테일은 채우지 않아도 되는데, 내 소개를 하면서 담을 만한 내용은, 이번 상하이 방문이 꽤나 spontaneous하게 결정되었고, 세렌디피티를 좋아하는 사람이어서 이번 방문을 통해 알게 된 여러분들과 앞으로도 유익하고 재밌는 콜라보레이션이나, 기회를 주고받는 것이 가능했으면 좋겠다고 생각한다 (MBTI: P)!
-->

<!--
이어서 작성할게.

일단 내 연구 배경 관련한 슬라이드를 담아낼 텐데, 너가 제시해 준 포인터 중 첫번째에 상당히 부합하는 것 같아서 이야기를 덧붙여. (일단 내가 반복적으로 끌리는 문제 구조가 무엇인가?, ) 결국 PI가 된 나는 현재 모델이 '어디까지 가능할 것이며', '아직 가능하지 않은 능력을 탑재하기 위해서는' 어떤 셋업에서 모델을 평가해야 원하는 방향의 연구가 이루어지는 지 고민하게 되는 것 같다.

LLM (ChatGPT, GPT4)가 이슈가 될 2023년 초부터 2024년 초반까지 무렵에 진행했던 Reasoning Capabilities of LLMs on ARC 연구의 경우가 좋은 예시가 될 것 같다, thinking LLM이 없었던 시절에 했던 3가지 측면을 잘 보여주기도 하지, 당시 했던 세 가지 질문: 1) 어떤 식으로 데이터를 넣어 주었을 때 LLM의 문제 풀이 능력을 끌어올릴 것이며, 2) prior 정보 를 (domain specific language) 넣어주었을 때 compositionality가 올라갈 수 있을 것인가, 3) LLM을 이용한 가상 데이터 생성이 가능하며 (rule을 잘 따르는 데이터가 나오는가), 그것이 비용적으로도 reasonable한가?는 후속 연구들로 하여금 다양한 생각의 확장을 가능케 했던 것 같아.

== 이 연구가 가졌던 직/간접적인 파급력을 마지막 것부터 이야기하자면
3) 일례로 ARC-AGI의 2024년 컴페티션을 마무리할 무렵에 리더보드의 형태가 accuracy 1개의 축만 있었던 것이 2개의 축으로 바뀌었는데, x축에는 각 문제당 사용한 토큰 비용($), y축에는 accuracy를 강조하는 형태로 옮겨지기도 하였고.

2) Compositionality를 고민하는 사람들 사이에서는 MDP를 활용하여 sequential한 decision making을 요구하는 방향으로 연구가 진행이 되기도 하였으며, (ARC-AGI라는 few shot input-output으로 보이는 문제를, domain specific language를 활용하여  제공해주고 program space 안에서 프로그램을 search하는 extrapolation 형태의 문제로 formulate하여 LDCQ (SOLAR) 연구까지 끌어오기도 하였고, LLM에 RL이 결합되는 커뮤니티의 방향성을 조금 일찍 짚어 냈다고 스스로 생각을 함 (당시 연구자들은 autoencoder 형태의 architecture가 알아서 해 주겠지 싶었던 때였으니까)

1) 우리가 만든 알고리즘이나 파이프라인을 어떻게 평가해야 올바른 평가인지 한층 깊게 고민해 볼 수 있게 하는 계기를 만들기도 하였다. (학습 시점에 input, output을 봤던 문제는 이미 memorization을 해 버렸기 때문에 output을 맞추는 평가재로 적절하지 않은데), 정답 program을 이용하여 input/output에 hard augmentation을 해 버리면, ARC-AGI의 discrete한 특성상 새로운 pair는 memorized된 예시가 더 이상 아니기 때문에, 단순한 pattern matching 기반으로 동작하는 모델들은 fail할 수밖에 없고, program induction을 해내야지만 평가가 가능해진다 (그 결과는 랜덤한 네 자릿수 곱셈을 못하는 LLM과 비슷했지).

(위 내용을 설명하기에 적절한 슬라이드 구성을 고민해 봐야겠다 - 논문의 그림을 넣어도 되고)

두번째 연구 내용을 전달하기에 앞서 이 정도 내용을 일단 md파일에 넣어보자

풀려고 하는 문제가 기술적으로  ) GIF-ARC

(일단 어떤 톡을 작성할 지 너가 결정을 해 보았는데, 내가 원하는 식으로
-->

<!--
ARC-AGI-1/2 연구를 진행했던 2024년에 많은 winner들, 90% 이상의 연구자들은 소위 pretraining stage의 성능을 끌어올리기 위한 생각들을 많이 했지 (BARC와 같이, 현재 모델이 어려워하였던 문제의 seed 놀리지를 기반으로 extrapolate를 수행한 프로그램 augmentation), 그리고 그 일부 결과물들을 이용한 pretrain 7b 모델들이 공개가 되기도 하였어.

여기서 많은 사람들이 간과했던 부분은, 리더보드 싸움을 하는 과정에 주어지는 시간 budget을 어떻게 사용할 것인데?에 해당하는 내용이었고, (Test-time augmentation), 결국 7b 수준의 모델에서는 그게 쉽지 않았는지 hard augmentation 및 test-time 에서의 데이터 증강을 통한 loss minimization 형태로 interpolate를 하는 시도등이 보였던 것 같아. (randaugment, ayurek - arc-prize 2024 2등)

사실 우리 연구실에서 고민했던 부분이 맞는 프레임이라고 생각했었거든. 결국 테스트 타임에서 어떤 방식으로 extrapolation을 해야할까? 고민하는 연구를 했었어. 우리가 ARCLE이라는 환경을 만듬과 동시에, 진행했던 LDCQ 연구나 model-based RL (dreamerV3 연구를 소개하고자 해) => sequential decision making이라고 표현을 한 것이었지만, 어쨌든 주어진 state와 이전 action history, 그리고 DSL들이 주어져 있을 때 - next action은 무엇을 골라야 하는 것인가? diffusion으로 생성해낸 latent를 바탕으로 q function - critic을 통해서 가장 좋은 policy를 찾아내게 하자는 연구를 2024년 초반부터 하였었고,, (ARCLE로 수행하였던 연구가 정확히 그것을 드러내는 느낌이지), 이게 사실상 2025년 1월에 나온 - 확인필요 - GRPO가 얘기하는 것과 크게 멀지 않았다고 생각한다.

GRPO가 나오고 나서, 이에 맞추어 포장을 하는 발표이기는 하지만, 연구를 수행하는 시점에는, 성과가 나올 지는 확실치 않지만 맞는 방향으로 가이드를 했던 것 같다 (표현 방식이 서툴러서 flag를 잘 꽂았는 지는 모르겠다고 생각함)
https://arxiv.org/abs/2410.11324
-->

<!--
어쨌든 하나하나 대학원생들이 진행하는 방법론 자체는 원하는 결과를 쉽게 증명하기 어려울 수도 있어. 하지만 풀어야 하는 problem definition으로 연구를 진행하게 된다면 - 그 방향으로 고민하는 사람들이 커뮤니티에서는 (다른 벤치마크지만) 충분히 있기 때문에 결국 커뮤니티에서는 그걸 가능케 하는 방법을 만들어 내게 되고 (그게 RLAIF, RLVR이라는 이름으로 알려지게 되었지), 그 과정을 멀리서 바라보았을 때, 내가 고민했던 문제 정의랑 맞아떨어졌을 때 느끼게 되는 쾌감은 PI로서 상당히 큰 것 같아.

그냥 가능하다고 알려진 방향에서 컴포넌트 하나를 조절했을 때, 좀더 좋은 성능을 낼 수 있었다는 식의 연구를 진행하는 경우가, 논문 한편을 출판하는 데 드는 코스트는 당연히 훨씬 작겠지. 학생들을 트레이닝 시키는 데 적절한 방법일 수도 있고. 그런데 그런 경우에는 그냥 one-of-them으로서 결과물을 하나 갖게 되는 것일 뿐이지, 지적 쾌감이 크지 않은 것 같아. 근데 맞는 문제, 아직 풀리지 않는 문제를 새로운 방향으로 도전했을 때, 나는 성공하지 않더라도 커뮤니티가 같은 방향으로 움직이면서 성공하는 모습을 보게 된다면, 내가 가정했던 디렉션이 결국 옳은 디렉션이었구나, 그와 함께 내 연구팀에서 구체화해 나가던 방법들이 어떤 한계점을 가졌는 지 배워 나가면서 연구자로 성장할 수 있게 되는 것 같아.
-->

<!--
다음으로는, 2025년에 Artificial General Intelligence 수업을 진행하면서 고민했던 방향 - tweaked MDP를 govern하는 rule을 인지하고, 해결해내는 meta-level 인지체를 만들 수 있는가?

사실 뉴럴넷에 너무 뇌가 절여진 학생들을 각성시키기 위한 숙제이기도 했지.
othello라는 게임을 잘 해결하는 agent를 알고 있는 뉴럴넷 architecture로 만들수 있니?
아주 간단한 positional heuristic에 비해 잘하는거 만들기는 쉽지 않을걸?  mobility란 개념이나 다양한 개념을 생각해서 advanced heuristics를 만들어보자. 그럼 맵을 줄테니까 그 맵에서 승리할 수 있는 strategy를 만들어봐. (알고있는 맵에 대한 strategy)
=> 여기까지가 hw1이었던 것 같아. 이쪽 분야를 찾아본 학생들은 MCTS 기반의 방법 등을 찾아오기도 하였지.

그런데 여기서 한 단계 꼬아서, hw2에서는 학습 시점에는 맵을 세개밖에 보여주지 않고, 평가 시점에 맵을 더 보여주겠다. 너가 만들어야 할 것은 모르는 맵에서 잘 작동하는 무언가를 만들어야 하는 것이야. 맵에 장애물이 추가될 수도 있어, 맵 크기가 변할 수도 있고, (또 너가 모르는 무언가의 룰이 추가될 수도 있어) 너가 제출해야 할 것은 intelligence system이 담겨있는 Javascript 코드이고, 그 코드는 unseen map을 탐사할 수 있는 시간으로 60초가 주어질 테니 60초를 최대한 활용해서 interaction을 수행한 후, tactic을 설계해. 학생들별 tactic들은 leaderboard에서 자웅을 겨룬 뒤 그 결과로 평가를 할거야.

AGI가 가지는 특징 중에서도 (다양한 게임들을 다루는 - multi-purpose와 같이 '암기'로 해결하는 불필요한 부분을 덜어내었고, 집중해야 할 부분을 명확히 정의해서 (skill-acquisition efficiency 중에서도 -- 주어진 stage에 담긴 model-dynamics를 파악하고, 내가 알고 있는 메타 게임 tactic을 주어진 stage에 맞게 modify하는 것), 학생들의 고민의 방향을 모으는 시도를 하였다.

오델로 벤치마크 명세는 arXiv:2508.09292에 있으며, Evolutionary learning을 position 기반 휴리스틱에 결합한 학생의 lightweight meta-solver 방법론은 현재 TMLR에 심사중이다.

(이 아이디어를 고민하고, 구체화하는 과정에서 다양한 완전 전략 보드게임을 잘하는 이승필 학생이 - Yinsh - yinsh.net이란 게임을 처음 맞닥뜨렸을 때 어떤 과정을 통해서 문제를 해결해 가는 지 살펴보았는데, 그 과정을 모사할 수 있는 에이전트를 만드는 방향으로 test-time model-based RL, 등의 연구를 이어나가고자 한 것 같다.)

---
-->

<!--
(벤치마크 관련해서 arXiv에 공개했던 초안은 2025년 5월에 neurips b&d에 처음 냈었으니까... 2025년 4월쯤 숙제가 나갔었던 것 같네.)  ARC-AGI-3 preview가 7월경 나왔으니, 동시대에 만들어진 벤치마크이다. ARC-AGI-3 preview를 보면서 - 내가 다루었던 문제 정의를 비슷하게 잘 다루었다는 점을 보면서 - 방향성에 일치가 주는 기쁨을 또다시 한번 느꼈던 것 같다.

---
-->

<!--
(이전 내용에 덧붙이기 -- 나도 오델로를 넘어서, 세균전 등으로 확장한 뒤에 다양한 게임에서 다양한 unknown map으로 확장한 후 숙제를 내고 싶었으나, javascript api등을 설정하는 과정에서 혼자 구현하기에는 벅찼던 것 같다 ㅋㅋㅋㅋ 결국 할 수 있는 범위 안에서 내게 됐네)

지금 내가 관심을 갖고 지켜보고  있는 연구 방향은 두 가지가 있다.
1) ARC-AGI-
-->

<!--
결국 내가 지금 관심을 가지고 지켜보고 있는 연구 방향은 두가지가 있는데
1) ARC-AGI-3를 해결해보기 (ARC-AGI-3를 해결해 나갈 수 있는 에이전트가 가지고 있는 역량을 직접 터치하는 방법론이 무엇일까 고민 - walkaround 형태로 ad-hoc하게 해결하는 방식을 원하지는 않음)
2) ARC-AGI-4에 대응되는 벤치마크에는 어떤 key factor를 가지고 있어야 할까? 결국 게임이라는 것 자체에 흥미를 가지는 agent는 어떤 게임이든 좀더 탐구하는 습성을 가질테고, 따라서 게임을 잘 하게 된 것이겠지 ? 좀더 넓게 봐서는 '호승심'이 강한 agent의 경우에는 이런 대결류 게임 벤치마크에서 더 집요하게 해 내는 경향이 있을 거야. 시키는 것만 잘 하는 것이 아닌 - 우리와 함께 나아가는 AI가 되려면, 혹은 우리가 못 푸는 문제를 해결해 주는 AI가 우리와 함께 한다면, 그런 AI들은 어떠한 high-level objective들이 govern해야만 할까? 그것이 만약 '생존 본능'이라면? => 생존 본능이 있는 agent들만 살아남을 수 있고, 그렇지 않는 agent들은 해결할 수 없는 아레나를 벤치마크화하여, next-generation ai에 필요한 것이 무엇일까 고민해볼 수 있는 시간을 갖고 싶다 (누군가는 benchmark가 존재한다는 것은 그쪽 방향으로의 gearing을 강제하기 때문에 overfitting이 발생한다고 이야기하지만 -- 이걸 cite해야할듯), 우리가 AI와 함께 살아갈 것이라는 것은 필수불가결한 수순일 것이기 때문에, 앞으로 우리와 함께할 AI가 가질 general intelligence를, 우리가 중요하게 여기는 가치에 근거해서 고민해 보는 것은 좋은 방향이 될 것 같다고 생각한다.
-->

<!--
(Yinsh라는 게임을 플레이하는 시간을 좀 가지면서 epistemic planning과 instrumental planning을 나눠서 판단해 보아도 될 것 같은데)

epistemic planning은 최대한 model dynamics을 파악하는 시간 - 이 규칙을 모르니 action X를 해서 효과를 관찰하자 (에이전트의 지식/믿음 상태(knowledge state) 를 바꾸는 것을 목표로)

instrumental planning은 고전적 의미의 planning에 가까운거 같아. 기본적인 작동 원리를 알았으니 / goal로 가기 위한 trajectory를 실행하자. (현재 상태를 목표 상태로 바꾸기 위한 행동 시퀀스를 찾기)
-->

<!--
Our Framing: ARC As a Abductive Reasoning
=> 이 부분이 하나 더 필요할 것 같아. ARC-AGI 문제의 본질이 무엇인가? 이 문제의 본질은 적은 개수의 예제를 보고 공통의 패턴을 도출하는 것이니까 => 모든 유사한 문제에 적용이 될 만한 basis가 되는 operator를 정의해 두고 (Michael hodel의 Domain specific language와 유사 = ARCLE의 action들), 각각의 pair를 만족시키는 프로그램을 high-level (grid)부터 low-level (pixel) recognition을 통해 induction을 한 이후에, 여러 pair를 모두 만족시키기 위한 anti-unification을 수행하여 - generalizable한 프로그램을 (most likely applicable) 생성해 내는 것을 목표하고 있다. 이런 과정들은 SOAR란 cognitive architecture에 근거하여, 문제를 풀어나가는 agent는 각각의 ARC-AGI task를 풀어나가는 와중에 procedural memory, episodic memory를 발전시켜 나가기를 희망하고 있다. 이 연구의 preminary version은 2024년 IJCAI (First International Workshop on Logical Foundations of Neuro-Symbolic AI)에 발표된 바 있다. https://arxiv.org/abs/2411.18158 (pipeline 사진을 공개하면 될거 같음)

=> 문제를 풀어가는 과정 또한 Symbolic한 구조체를 hierarchical (high-level부터 low-level)까지 만들어서 풀어내고 있는 데, 그 과정을 꼭 symbolic한 형태로 진행하지는 않아도 될 것으로 보임.
그동안 막혀 있었던 부분이 너무 symbolic dependent였다면, frontier model의 harnessing을 통해서 좀더 유연하게 접근할 수 있을 것으로 보임.
-->

# MSRA Talk

## Working Title

- From Summary to Shared Research Directions
- A discussion-first talk on what we could build together

## Core Intent

이 톡의 목적은 내가 지금까지 해 온 연구를 여러 개 나열해 요약하는 것이 아니라, 앞으로 함께 해볼 수 있는 문제의 형태와 협업의 가능성을 탐색하는 것이다. 즉, 완결된 결과를 전달하는 세미나보다는 몇 가지 좋은 포인터를 던지고, 그 포인터를 중심으로 대화를 열어두는 디스커션 중심의 톡으로 설계한다.

## Tone

- summary-heavy seminar가 아니라 discussion-enabling talk
- polished conclusion보다 promising directions
- one-way presentation보다 shared exploration

## Suggested Flow

### 1. Quick Personal Intro

- 이번 상하이 방문은 꽤 spontaneous하게 결정되었다.
- 나는 serendipity를 좋아하는 편이고, 예상하지 못한 만남에서 일이 커지는 순간들을 즐긴다.
- 이번 방문을 계기로 알게 된 분들과 이후에도 유익하고 재미있는 collaboration, 그리고 서로에게 기회를 열어주는 관계가 이어지면 좋겠다.
- MBTI로 치면 꽤 P적인 사람이라는 정도로 가볍게 마무리할 수 있다.

### 2. Why This Talk Exists

- 오늘은 completed story를 전달하러 왔다기보다, 같이 생각해볼 수 있는 space를 만들고 싶다.
- 제 관심사는 특정한 한 프로젝트 자체보다도, 어떤 문제는 같이 밀면 더 빨리 흥미로워지는가에 가깝다.
- 그래서 몇 개의 neatly packaged results보다, collaboration-worthy questions를 중심으로 이야기하고자 한다.

### 3. What Kind of Conversation I Want

- 어떤 문제는 지금 당장 같이 시작해볼 수 있는가
- 어떤 문제는 서로 다른 강점이 결합될 때 더 재밌어지는가
- 어떤 포맷의 collaboration이 현실적으로 가장 자연스러운가
- short-term exploration과 longer-term agenda를 어떻게 같이 가져갈 수 있는가

### 4. Pointers Instead of Full Survey

이 부분에서는 여러 연구를 길게 리뷰하기보다, 아래와 같은 형식으로 3개 내외의 포인터만 제시하는 편이 적절하다.

- pointer 1: 내가 반복적으로 끌리는 문제 구조는 무엇인가
- pointer 2: 지금 시점에서 기술적으로 가능성이 커 보이는 방향은 무엇인가
- pointer 3: 혼자 하기보다 같이 할 때 의미가 커지는 질문은 무엇인가

각 포인터는 다음 네 줄 안팎으로 정리한다.

- Why it is interesting
- Why now
- What makes it hard
- What collaboration could unlock

## Pointer 1: What Problems I Keep Coming Back To

결국 내가 반복적으로 끌리는 문제는, 현재의 모델이 어디까지 가능한지 확인하는 일과 아직 불가능한 능력을 정말 배우게 하려면 어떤 평가 셋업이 필요한지 설계하는 일이다. 이제 PI의 입장에서 보면, 중요한 것은 단순히 성능을 한 번 끌어올리는 것이 아니라 어떤 evaluation setup이 연구자들을 원하는 방향으로 밀어주는가를 고민하는 것에 더 가깝다.

이 포인터는 다음 질문으로 요약될 수 있다.

- 현재 모델은 어디까지 할 수 있는가
- 아직 없는 능력을 드러내려면 어떤 태스크와 평가가 필요한가
- 어떤 셋업이 단순한 memorization이 아니라 real capability를 요구하게 만드는가

## Research Background Example

### Reasoning Capabilities of LLMs on ARC

2023년 초부터 2024년 초반, 아직 thinking LLM이 본격화되기 전 시점에 진행한 Reasoning Capabilities of LLMs on ARC 연구는 위 문제의식을 잘 보여주는 사례다. 당시의 핵심은 ARC를 단순히 "LLM이 몇 문제를 맞히는가"로 보는 것이 아니라, 어떤 입력 표현과 어떤 prior, 그리고 어떤 데이터 생성 방식이 reasoning capability를 실제로 끌어낼 수 있는가를 묻는 것이었다.

당시의 질문은 크게 세 가지였다.

1. 어떤 방식으로 데이터를 제시해야 LLM의 문제 해결 능력을 가장 잘 끌어낼 수 있는가
2. domain specific language 같은 prior를 제공했을 때 compositionality를 더 잘 발현시킬 수 있는가
3. LLM으로 규칙을 잘 따르는 synthetic data를 만들 수 있는가, 그리고 그 비용은 reasonable한가

## Why This Example Matters In The Talk

이 사례는 단순히 예전 프로젝트 하나를 소개하는 용도가 아니라, 내가 어떤 종류의 문제를 중요하게 보는지를 압축해서 보여주는 예시로 사용할 수 있다. 즉, 모델 architecture 자체보다도 다음 질문을 먼저 묻는 관점을 드러낸다.

- capability를 끌어내는 representation은 무엇인가
- compositional generalization을 유도하는 prior는 무엇인가
- 미래 연구를 자극하는 evaluation axis는 무엇인가

## Indirect And Direct Impact

이 연구의 파급력은 세 번째 질문에서 첫 번째 질문 방향으로 거슬러 올라가며 설명하면 흐름이 자연스럽다.

### A. Cost-Aware Evaluation Became A Real Axis

- ARC-AGI 2024 competition 말미에는 leaderboard가 accuracy 단일 축에서 accuracy와 token cost를 함께 보는 구조로 이동했다.
- x축에 문제당 사용 토큰 비용, y축에 accuracy를 두는 framing은 단지 점수를 높이는 것이 아니라 얼마나 economically sensible한 방법인가를 함께 보게 만들었다.
- 즉, synthetic data generation과 inference cost를 함께 고민한 문제의식이 이후 benchmark framing에도 간접적으로 반영되었다고 이야기할 수 있다.

### B. Compositionality Led Toward Sequential Decision Making

- compositionality를 제대로 다루려면 정적인 pattern matching보다 sequential decision making이 필요하다는 방향이 점차 분명해졌다.
- 그 결과 ARC-AGI를 few-shot input-output matching 문제가 아니라, domain specific language 위에서 program space를 search하는 extrapolation 문제로 다시 formulate하는 흐름이 나왔다.
- 이 문제의식은 이후 MDP framing이나 LDCQ, SOLAR 류의 연구와도 자연스럽게 닿아 있다.
- 뒤늦게 보면, LLM과 RL의 결합이 중요해질 방향을 비교적 이른 시기에 짚은 셈이라고 정리할 수 있다.

### C. It Forced A Better Question About Evaluation

- 어떤 알고리즘이나 파이프라인을 평가할 때, 학습 시점에 이미 본 input-output pair를 다시 맞히게 하는 것은 좋은 평가가 아니다.
- ARC-AGI에서는 정답 program을 이용한 hard augmentation이 특히 의미 있었는데, discrete한 문제 구조 덕분에 새로운 input-output pair는 더 이상 memorized example이 아니다.
- 따라서 단순한 pattern matching으로는 실패할 수밖에 없고, 실제로는 program induction에 가까운 능력이 있어야 성능이 나온다.
- 이 점은 랜덤한 네 자릿수 곱셈을 안정적으로 하지 못하는 당시 LLM의 한계와 비슷한 감각으로 연결해 설명할 수 있다.

## Suggested Slide Composition For This Part

### Slide: Research Taste / What I Keep Optimizing For

- 내가 반복적으로 끌리는 질문은 model capability의 frontier와 evaluation design 사이의 관계다.
- 좋은 연구 문제는 모델을 더 똑똑하게 만드는 것뿐 아니라, 무엇을 평가해야 진짜 능력이 드러나는지를 다시 정의한다.

### Slide: ARC As An Early Example

- Reasoning Capabilities of LLMs on ARC를 early case study로 제시
- 당시의 세 가지 질문을 1, 2, 3으로 간단히 배치
- 가능하면 논문 figure 한 장으로 입력 표현 또는 전체 파이프라인을 시각화

### Slide: Why Those Three Questions Mattered

- representation
- prior / compositionality
- synthetic data and cost

이 슬라이드는 "이 세 질문이 이후 어떤 연구 방향을 열었는가"를 보여주는 bridge 역할로 둔다.

### Slide: Impact On The Field And On My Thinking

- evaluation axis expanded from accuracy to accuracy plus cost
- compositionality research moved toward search, MDP, and RL-flavored framing
- evaluation became less about memorized outputs and more about induced programs

## Visual Ideas

- 논문 figure를 그대로 가져와서 세 가지 질문을 annotation으로 덧붙이기
- leaderboard 축 변화가 보이는 그림이나 간단한 schematic 넣기
- original pair와 hard-augmented pair를 대비시키는 toy example 넣기

## Bridge To The Next Research Topic

다음 연구로 넘어갈 때는 "그래서 나는 계속 capability 자체보다 capability를 드러내는 task design과 evaluation design에 관심이 간다"라는 문장으로 연결하면 자연스럽다.

현재 다음 주제로는 GIF-ARC를 후보로 두고, 기술적으로 풀고 싶은 문제가 무엇인지 이어서 정리하면 된다.

## 2024 ARC Landscape: Pretraining Versus Test-Time Strategy

ARC-AGI-1과 2를 둘러싼 2024년의 큰 흐름을 보면, 많은 상위권 팀과 연구자들은 pretraining stage에서 성능을 끌어올리는 방향에 집중했다. 대표적으로 BARC류의 접근처럼, 모델이 어려워하던 문제 seed를 바탕으로 program augmentation을 수행하고, 그 결과물을 이용해 추가 pretraining을 하는 방식이 주류였다. 실제로 일부 결과물은 7B 규모의 pretrained model 형태로 공개되기도 했다.

하지만 여기서 상대적으로 덜 주목받은 질문이 있었다. 리더보드 경쟁에서 주어진 time budget을 테스트 시점에 어떻게 쓸 것인가 하는 문제다. 즉, 학습 전 단계에서 capability를 밀어 넣는 것만큼이나, test-time augmentation과 search budget allocation을 어떻게 설계하느냐가 중요하다는 관점이다.

당시 7B 수준의 모델에서는 이 test-time extrapolation이 쉽지 않았고, 그 결과 hard augmentation이나 test-time data augmentation을 통해 loss minimization 형태의 interpolation을 시도하는 접근들이 등장했다. 이 대목에서는 randaugment 계열이나 Ayurek 팀의 ARC Prize 2024 2등 접근을 예시로 언급할 수 있다.

## Why Our Lab Focused On Test-Time Extrapolation

우리 연구실은 이 지점에서 프레임 자체는 맞았다고 생각했다. 핵심 질문은 "테스트 타임에 어떤 방식의 extrapolation을 수행할 것인가"였다. 단지 더 큰 사전학습 모델을 만드는 것이 아니라, 주어진 state와 action history, 그리고 DSL이 있을 때 다음 action을 어떻게 선택해야 하는가를 푸는 문제로 보자는 접근이다.

이 문제를 우리는 sequential decision making이라는 언어로 정리했고, ARCLE 환경과 LDCQ, 그리고 model-based RL 계열의 문제의식으로 연결해 왔다. 그 관점에서 ARC는 단순한 static puzzle이 아니라, latent state를 구성하고 critic 또는 Q-function을 이용해 더 나은 policy를 찾는 의사결정 문제로 읽힌다.

## ARCLE, LDCQ, And The Offline RL Framing

2024년 초반부터 진행한 연구의 핵심은 다음과 같이 정리할 수 있다.

- ARCLE은 ARC를 sequential interaction environment로 드러내는 역할을 했다.
- LDCQ와 SOLAR는 충분한 trajectory data를 구성해 offline RL이 작동할 수 있는 기반을 제공했다.
- diffusion으로 만든 latent representation 위에서 critic-guided policy improvement를 수행한다는 관점은, test-time에서 무엇을 시도할지 선택하는 문제와 직접 연결된다.

이 흐름은 나중에 GRPO류의 framing이 대중화된 뒤 다시 보면 상당히 멀지 않은 방향으로 읽힌다. 다만 여기서는 과장하지 않는 편이 좋다. "동일한 방법을 먼저 했다"기보다, capability를 one-shot prediction이 아닌 trajectory-level decision problem으로 보려는 관점을 비교적 일찍 붙잡고 있었다고 정리하는 편이 더 정확하다.

## Another Framing: ARC As An Abductive Reasoning Problem

동시에 ARC-AGI를 sequential decision making으로만 보는 것도 충분하지 않다. ARC의 더 고전적인 본질은, 적은 수의 예제를 보고 공통의 규칙을 설명할 수 있는 가장 그럴듯한 프로그램을 찾아내는 abductive reasoning 문제라는 점에 있다. 즉 각 input-output pair를 개별적으로 맞히는 것이 아니라, 여러 pair를 동시에 설명할 수 있는 latent operator set과 transformation program을 유도해야 한다.

이 관점에서는 먼저 유사한 문제들에 반복적으로 적용될 수 있는 basis operator를 정의해 두고, 각 pair에 대해 high-level grid structure부터 low-level pixel relation까지 내려가며 candidate program을 induction한다. 그 뒤 여러 pair를 모두 만족시키는 쪽으로 anti-unification을 수행해, 가장 generalizable하고 most likely applicable한 프로그램을 얻는 것이 핵심이 된다. Michael Hodel의 DSL 계열 접근이나 ARCLE의 action space도 이 관점에서 이해할 수 있다. 결국 중요한 것은 단일 예시를 설명하는 ad-hoc rule이 아니라, 여러 예시를 관통하는 공통 구조를 얼마나 잘 끌어내느냐다.

이 문제의식은 SOAR 같은 cognitive architecture를 참조한 abductive symbolic solver 흐름과도 연결된다. 여기서는 문제를 푸는 과정에서 agent가 procedural memory와 episodic memory를 함께 발전시켜 나가기를 기대한다. 2024년 IJCAI LNSAI Workshop에 발표된 preliminary version인 Abductive Symbolic Solver on Abstraction and Reasoning Corpus도 이런 방향 위에 서 있다. 발표에서는 이 논문의 pipeline figure를 한 장 보여주면서, ARC를 단순한 pattern completion이 아니라 hypothesis generation, program induction, anti-unification의 연쇄로 보는 관점을 짚어주면 좋다.

다만 지금 시점에서 중요한 것은 이 전체 과정을 반드시 fully symbolic하게만 구현할 필요는 없다는 점이다. 그동안 막혔던 부분 중 일부는 symbolic dependency가 너무 강했다는 데 있을 수 있다. 이제는 hierarchical symbolic structure를 problem representation의 scaffold로 유지하되, frontier model의 harnessing을 이용해 더 유연하게 candidate hypothesis를 만들고, 더 robust하게 abstraction level을 오가도록 설계할 수 있다. 즉 symbolic structure와 frontier model reasoning을 대립항으로 둘 필요는 없고, 오히려 abductive solver를 더 실용적으로 만들기 위한 결합점으로 볼 수 있다.

## Citation Check Note

- 사용자가 남긴 arXiv 링크는 GRPO 논문이 아니라 Diffusion-Based Offline RL for Improved Decision-Making in Augmented ARC Task (arXiv:2410.11324)다.
- 따라서 발표에서는 이 논문을 ARCLE, SOLAR, LDCQ 흐름의 예시로 쓰고, GRPO와의 연결은 별도 citation 확인 후 언급하는 편이 안전하다.

## How To Present This Without Overclaiming

- 당시에는 성과가 확실하지 않았더라도, 연구 방향을 capability frontier의 관점에서 먼저 제시했다는 점을 강조한다.
- hindsight를 이용해 "지금 보니 맞았다"고 말할 수는 있지만, "우리가 이미 같은 것을 했다"고 강하게 claim하지는 않는다.
- 더 적절한 표현은 "we were trying to formulate the right problem before the community had a stable name for it"에 가깝다.

## Research Philosophy As A PI

여기서 한 단계 더 강조하고 싶은 것은, 개별 방법론이 당장 원하는 결과를 증명하지 못하더라도 problem definition이 맞다면 그 자체로 연구적 가치가 크다는 점이다. 한 연구실이 제안한 구체적 방법이 바로 정답이 아닐 수는 있다. 하지만 커뮤니티 전체가 같은 문제를 중요한 문제로 받아들이기 시작하면, 다른 벤치마크와 다른 이름 아래에서도 결국 그 방향을 가능하게 하는 방법들이 등장한다.

이 관점에서 보면 RLAIF나 RLVR 같은 흐름도, 이름과 구현은 달라도 "어떤 capability를 드러내고 어떤 reasoning-time process를 최적화할 것인가"라는 더 큰 문제 정의 위에서 이해할 수 있다. 멀리서 커뮤니티의 움직임을 보다가, 예전에 내가 중요하다고 생각했던 문제 정의와 나중의 성공적인 흐름이 맞아떨어지는 순간에 느끼는 지적 쾌감은 PI에게 매우 크다.

## Why This Matters More Than Small Component Wins

물론 이미 가능하다고 알려진 방향에서 컴포넌트 하나를 조정해 성능을 조금 더 높이는 연구는 출판 비용이 더 낮고, 학생을 빠르게 훈련시키는 데에도 유용할 수 있다. 그런 연구가 불필요하다는 뜻은 아니다. 다만 그런 방식은 종종 one-of-them으로서 결과물을 하나 더하는 일에 가까워지고, 문제를 새롭게 정의했을 때 얻는 지적 보상과는 종류가 다르다.

반대로 아직 풀리지 않은 문제를 향해 새로운 framing을 제안하는 연구는 실패 가능성이 더 크다. 그렇지만 설령 내 연구팀의 구체적 방법이 최종적으로 승리하지 않더라도, 커뮤니티가 결국 같은 방향으로 움직이며 그 문제를 풀어내는 모습을 보면 두 가지를 동시에 얻게 된다.

- 내가 중요하다고 본 direction이 옳았다는 확인
- 우리 팀이 시도한 방법의 한계가 무엇이었는지에 대한 학습

그 과정 자체가 연구자로서의 성장을 만들어 준다는 점을 톡에서 분명히 드러낼 수 있다.

## A Useful Contrast To Say Out Loud

- low-risk work: known direction 안에서 component를 조절해 measurable gain을 얻는 연구
- high-conviction work: 아직 덜 정식화된 문제를 먼저 붙잡고, 맞는 evaluation과 action space를 정의하려는 연구

이 대비를 넣으면, 왜 내가 ARC나 reasoning-time compute, sequential decision making 같은 문제에 반복적으로 끌리는지가 훨씬 선명해진다.

## Suggested Slide: What I Find Intellectually Rewarding

- not just improving a known recipe
- defining the right problem before the method is obvious
- learning from whether the community later moves in the same direction

이 슬라이드는 개인적 취향 고백처럼 들리면서도, 동시에 앞으로 어떤 collaboration을 선호하는지 알려주는 역할을 한다.

## Suggested Slide: A PI's Version Of Success

- success is not only publishing a paper quickly
- success is also identifying a problem the field will eventually care about
- even when our first method is imperfect, the framing can still be right

이 장은 앞선 ARCLE, LDCQ, SOLAR 이야기를 정리하면서 다음 섹션의 collaboration discussion으로 넘어가는 bridge로 쓰기 좋다.

## 2025 AGI Course: Can We Build A Meta-Level Agent?

2025년에 Artificial General Intelligence 수업을 진행하면서 더 분명해진 질문이 있다. tweaked MDP를 govern하는 rule을 인지하고, 그 rule에 맞춰 행동 전략을 재구성할 수 있는 meta-level agent를 만들 수 있는가 하는 질문이다. 이건 단순히 특정 게임 하나를 잘 푸는 에이전트를 만드는 문제보다 한 단계 위의 문제다. 주어진 환경의 dynamics를 파악하고, 이미 알고 있는 tactic을 상황에 맞게 수정하는 능력을 물어보는 셈이다.

이 문제 설정은 동시에 학생들의 사고를 architecture-first 관성에서 떼어내기 위한 숙제이기도 했다. 뉴럴넷을 하나 더 쌓는 방식만으로는 쉽게 해결되지 않는 문제를 던지고 싶었다. 즉, "어떤 모델을 쓰지"보다 "문제를 어떻게 읽고, 규칙을 어떻게 파악하고, 어떤 탐사 전략을 쓸 것인가"를 먼저 고민하게 만드는 것이 목적이었다.

## Homework 1: Solve A Known Map Well

첫 번째 숙제는 비교적 익숙한 setting이었다. Othello 같은 게임을 잘 해결하는 agent를 만들 수 있는가를 묻되, 단순한 end-to-end neural policy보다 positional heuristic, mobility, advanced heuristic 같은 개념을 먼저 생각하게 했다. 맵이 주어졌을 때 그 맵에서 실제로 이길 수 있는 strategy를 설계해 보라는 문제였다.

이 단계에서는 이미 알려진 맵에 대한 전략을 잘 세우는 것이 핵심이었다. 학생들 중 일부는 이 과정에서 MCTS 기반 접근을 찾아오기도 했다. 숙제의 목적은 성능 숫자 자체보다도, 무엇이 지능적인 접근인지에 대한 감각을 복원하는 데 있었다.

## Homework 2: Build Something That Survives The Unknown

두 번째 숙제에서는 문제를 한 단계 꼬았다. 학습 시점에는 세 개의 맵만 보여주고, 평가 시점에는 더 많은 unseen map을 주는 방식이었다. 맵에 장애물이 추가될 수도 있고, 맵 크기가 바뀔 수도 있으며, 학생이 알지 못한 rule variation이 들어갈 수도 있다는 설정이었다.

학생들이 제출해야 하는 것은 정답 목록이 아니라 intelligence system이 담긴 JavaScript 코드였다. 이 코드는 unseen map을 탐사할 수 있는 60초의 interaction budget을 부여받고, 그 시간을 최대한 활용해 환경을 파악한 뒤 tactic을 설계해야 했다. 즉, 여기서 평가되는 것은 memorization이 아니라 rapid model-building과 adaptation의 능력이다.

## What This Benchmark Was Trying To Isolate

AGI의 여러 특징 중에서도 여기서 특히 분리해 보고 싶었던 것은, 불필요한 암기 요소를 줄인 상태에서 skill-acquisition efficiency를 어떻게 측정할 것인가 하는 점이었다. 더 정확히 말하면 다음 질문에 가깝다.

- 주어진 stage가 따르는 model dynamics를 얼마나 빨리 파악할 수 있는가
- 이미 알고 있는 meta-game tactic을 현재 stage에 맞게 얼마나 잘 수정할 수 있는가
- interaction budget을 단순 탐색이 아니라 hypothesis formation에 쓸 수 있는가

이 점에서 이 과제는 다종 게임을 잘하는 범용 agent를 묻는 문제이면서도, 동시에 reasoning-time adaptation을 얼마나 잘 하느냐를 보는 benchmark였다.

## Why This Felt Aligned With ARC-AGI-3 Preview

벤치마크 관련 초안을 arXiv에 공개하기 전, 2025년 4월 무렵 수업 숙제로 이미 이 문제를 밀어보고 있었고, 5월에는 NeurIPS B&D 쪽으로 초안을 냈던 흐름으로 이해하면 된다. 이후 7월경 ARC-AGI-3 preview를 보면서, 내가 다루고 있던 문제 정의와 상당히 비슷한 방향을 잘 짚고 있다는 인상을 받았던 것 같다.

여기서 다시 한 번 중요했던 것은 개별 benchmark의 우열보다도 방향성의 합치였다. unseen environment에서 빠르게 rule을 파악하고, 기존 tactic을 수정하며, test-time interaction budget을 적극적으로 사용해야 한다는 framing이 같은 시기에 다른 곳에서도 부상하고 있다는 사실 자체가 의미 있었다.

## Implementation Constraints Were Also Real

사실 개인적으로는 Othello를 넘어서 세균전 같은 게임이나 더 다양한 unknown map setting으로 과제를 확장하고 싶었다. 여러 완전정보 보드게임을 아우르는 더 넓은 benchmark를 만들고 싶었지만, JavaScript API와 evaluation harness를 혼자 다 세팅하는 데에는 현실적인 한계가 있었다. 그래서 최종적으로는 구현 가능한 범위 안에서 숙제를 냈다.

이 점도 발표에서는 솔직하게 말할 수 있다. problem definition은 더 크게 가져가되, 실제 benchmark는 리소스 제약 아래에서 만든 한 버전의 concrete instantiation이었다는 식이다.

## Human Problem Solving As A Design Clue

이 아이디어를 구체화하는 과정에서는, 완전 전략 보드게임을 잘하는 학생이 처음 보는 게임을 만났을 때 어떤 방식으로 문제를 풀어 가는지를 관찰한 경험도 중요한 힌트가 되었다. 예를 들어 Yinsh 같은 게임을 처음 접했을 때, 인간 플레이어는 규칙을 빠르게 파악하고, 가설을 세우고, tactical template을 수정해 나간다.

이 관찰은 이후 test-time model-based RL이나 search-augmented agent를 통해, 환경과 상호작용하면서 내부 모델을 세우고 policy를 업데이트하는 연구로 이어질 수 있다는 감각을 주었다.

## Why This Example Belongs In The Talk

ARC, GIF-ARC, 그리고 이 AGI 수업의 benchmark는 겉으로는 달라 보이지만, 실제로는 같은 질문을 공유한다.

- intelligence는 정답을 많이 외운 상태인가
- 아니면 새로운 rule과 state transition을 빠르게 읽고, 적절한 abstraction을 만들며, search와 action을 조정하는 과정인가

내가 계속 붙잡는 쪽은 분명히 후자다. 그래서 이 사례는 단순한 수업 과제 소개가 아니라, 내가 무엇을 intelligence의 핵심으로 보는지 다시 보여주는 예시로 쓸 수 있다.

## Two Directions I Am Watching Now

결국 지금 내가 가장 관심을 가지고 지켜보고 있는 연구 방향은 두 가지다. 하나는 당장 눈앞의 어려운 benchmark를 정면으로 건드리는 것이고, 다른 하나는 그 다음 세대 benchmark가 무엇을 측정해야 하는지를 다시 정의하는 일이다.

## Direction 1: Solving ARC-AGI-3 Without Cheap Workarounds

첫 번째는 ARC-AGI-3를 정말로 풀어보는 것이다. 여기서 중요한 것은 단순히 score를 올리는 것이 아니라, ARC-AGI-3를 풀 수 있는 agent가 실제로 어떤 역량을 가져야 하는지를 직접 건드리는 방법론이 무엇인가를 묻는 일이다.

내가 원하지 않는 것은 walkaround 형태의 ad-hoc solver다. 즉, benchmark의 표면적 패턴이나 loophole을 파고들어 점수를 얻는 방식보다는, rule inference, abstraction building, hypothesis testing, test-time adaptation 같은 핵심 능력에 실제로 접근하는 방법을 찾고 싶다.

지금 arc-agi-3 디렉토리 안의 master-plan에서 잡아둔 방향도 정확히 여기에 있다. ARC-AGI-3를 next-action prediction 문제로 보지 않고, problem solving 과정 안에서 world model을 세워 가는 과제로 보자는 것이다. 64x64 그리드를 4096개의 픽셀로 다루기보다 object와 object 관계의 장면으로 읽고, action 이후 어떤 object가 어떤 규칙으로 변했는지를 작은 실행 가능한 가설로 코드화해 나가는 쪽에 더 가깝다. 즉, 먼저 이해하고 그 다음 계획하는 것이지, 이해 없이 행동열만 맞히는 방식으로는 가고 싶지 않다.

그래서 하네스도 단순한 action loop가 아니라, scene analysis, object tracking, hypothesis management, prediction, surprise monitoring, planning이 분리된 구조를 지향하고 있다. 초반 몇 step의 목적은 정답 경로를 바로 찾는 것이 아니라 가장 정보량이 높은 실험을 통해 dynamics를 드러내는 것이고, 어느 정도 world model이 안정된 다음에야 solve-oriented planning으로 넘어가야 한다. 이 점에서 중요한 것은 epistemic planning과 instrumental planning을 분리하는 것이다. 처음에는 "무슨 일이 일어나는가"를 알아내기 위한 행동이 우선이고, 그 뒤에야 "어떻게 클리어할 것인가"를 계산하는 것이 자연스럽다.

여기서 epistemic planning은 에이전트의 knowledge state를 바꾸는 것을 목표로 하는 planning이다. 아직 규칙을 모르기 때문에, action X를 해 보고 어떤 효과가 나타나는지를 관찰함으로써 model dynamics를 최대한 빨리 파악하려는 시간이다. 반면 instrumental planning은 훨씬 고전적인 의미의 planning에 가깝다. 기본적인 작동 원리와 제약을 어느 정도 이해한 뒤에는, 현재 상태를 goal state로 바꾸기 위한 trajectory를 계산하고 실행해야 한다. 같은 action 선택 문제처럼 보여도, 전자는 belief update가 목적이고 후자는 state transition control이 목적이라는 점에서 서로 다른 종류의 사고다.

이 구분은 Yinsh 같은 새로운 게임을 처음 접할 때도 직관적으로 드러난다. 초반에는 "이 말은 어떻게 움직이지", "라인이 만들어지면 정확히 무슨 일이 일어나지", "어떤 수가 irreversible한가"를 알아보기 위해 일부러 실험적인 수를 두게 되는데, 이것이 epistemic planning에 가깝다. 반대로 규칙과 tactical pattern이 어느 정도 이해된 뒤에는, 이제는 실제 승리를 위해 어떤 수순을 밟아야 하는지 계산하게 되는데 이것이 instrumental planning이다. 내가 ARC-AGI-3나 unknown-map benchmark에서 보고 싶은 것도 바로 이런 전환이다.

또 하나 중요한 것은 이 전체 과정을 작은 모델에게도 이식 가능한 형태로 남겨야 한다는 점이다. 그래서 master-plan에서는 environment 구현을 읽지 않는 정보 경계를 고정하고, 관찰, 예측, 실패, 가설 수정의 로그를 남기는 것을 핵심 산출물로 보고 있다. 나중에 Qwen 4B 같은 작은 모델로 옮길 때도, raw grid를 그대로 넣는 것보다 object-centric summary, motif hypothesis, action effect classification, prediction-and-revision trace를 supervision으로 주는 편이 훨씬 현실적이다. 내가 보고 싶은 ARC-AGI-3 solver는 결국 점수만 내는 시스템이 아니라, 세계를 어떻게 이해했고 왜 그 행동을 골랐는지 설명 가능한 형태로 남기는 시스템이다.

이 관점에서 ARC-AGI-3는 단순한 competition target이 아니라 다음 질문을 위한 probe로 볼 수 있다.

- 어떤 능력이 없으면 이 benchmark를 안정적으로 풀 수 없는가
- 그 능력을 직접 학습하거나 유도하는 training and evaluation setup은 무엇인가
- search, interaction, world modeling, self-correction 중 무엇이 본질적인 bottleneck인가

## Direction 2: What Should ARC-AGI-4 Measure?

두 번째는 더 앞의 질문이다. ARC-AGI-4에 해당하는 next-generation benchmark는 어떤 key factor를 가져야 하는가?

여기서는 단순히 더 어려운 puzzle을 만드는 것보다, 어떤 high-level objective를 가진 agent가 더 일반적인 지능을 발휘하는가를 물어보고 싶다. 예를 들어 게임 자체에 흥미를 느끼는 agent는 다양한 게임을 더 집요하게 탐구할 가능성이 높고, 그 결과 더 잘하게 될 수 있다. 더 넓게 보면, 강한 호승심을 가진 agent는 competitive benchmark에서 더 오래 버티고 더 많이 시도할 수 있다.

따라서 질문은 자연스럽게 다음으로 넘어간다. 시키는 것만 잘하는 AI가 아니라, 우리와 함께 나아가고 우리가 못 푸는 문제를 함께 해결하는 AI를 원한다면, 그런 AI는 어떤 high-level objective들에 의해 govern되어야 하는가?

## A More Radical Benchmark Question

만약 그 objective 중 하나가 생존 본능에 가까운 것이라면 어떨까? 생존 본능이 있는 agent들만 살아남을 수 있고, 그렇지 않은 agent들은 통과하지 못하는 arena를 benchmark화할 수 있을까? 이런 질문은 다소 과감해 보이지만, next-generation AI에 정말 필요한 것이 무엇인가를 생각하게 만든다.

이 방향의 핵심은 단순히 난도를 높이는 것이 아니라, agent가 스스로 더 집요하게 탐구하고, 더 오래 버티고, 더 강한 동기를 가지고 문제를 파고드는 성질을 evaluation 안으로 끌어오는 데 있다.

## Why This Matters Beyond Benchmark Design

누군가는 benchmark가 존재하는 순간 그 benchmark 방향으로의 gearing이 강제되고, 결국 overfitting이 생긴다고 말할 수 있다. 이 비판은 진지하게 다뤄야 한다. 다만 그럼에도 불구하고 어떤 benchmark를 설계하느냐는, 우리가 어떤 방향의 지능을 중요하게 여기는지를 공개적으로 선언하는 행위이기도 하다.

AI와 함께 살아가게 되는 흐름이 사실상 피할 수 없는 수순이라면, 앞으로 우리와 함께할 AI가 어떤 general intelligence를 가져야 하는지, 그리고 그 intelligence가 어떤 가치와 objective 위에 서 있어야 하는지를 미리 고민하는 것은 충분히 정당한 연구 방향이다.

## A Good Way To Say This In The Talk

- one direction is to solve the benchmark in front of us honestly
- the other is to ask what the next benchmark should force us to care about
- the second question is ultimately a question about the kind of intelligence we want to live with

이 부분은 발표의 마지막에서 collaboration discussion으로 넘어가기 전에 던지는 질문으로도 좋다. 단지 "무엇을 할 수 있나"가 아니라 "어떤 AI를 만들고 싶은가"를 함께 묻게 만들기 때문이다.

## Suggested Slides For This Part

### Slide: What Most People Optimized In 2024

- pretraining-oriented augmentation
- synthetic programs and expanded training corpora
- stronger 7B-scale solvers via data generation

### Slide: The Missing Question

- what should we do with test-time budget
- how should a solver spend compute at inference time
- can extrapolation be decided, not just memorized

### Slide: Our Framing

- ARC as sequential decision making
- state + action history + DSL -> next action
- test-time reasoning as policy selection rather than static prediction

### Slide: Another Framing: ARC As An Abductive Reasoning Problem

- infer a shared program from only a few input-output examples
- induce candidate explanations per pair, then anti-unify across pairs
- the goal is not ad-hoc fit, but the most generalizable program

### Slide: From Symbolic Structure To Frontier Harnessing

- hierarchical symbolic structures are still useful scaffolds
- but the whole pipeline need not stay fully symbolic
- frontier models may make the abductive search more flexible

### Slide: ARCLE / LDCQ / SOLAR

- ARCLE as environment
- SOLAR as trajectory source
- LDCQ as offline RL mechanism for better decision making

### Slide: Connection To Later RL-for-Reasoning Trends

- avoid direct equivalence claims
- emphasize early framing around trajectory-level optimization
- position this as a useful bridge to broader discussion on reasoning-time compute

### Slide: What I Find Intellectually Rewarding

- choosing the right problem can matter more than winning early on the method
- community convergence is a strong signal that the framing was meaningful
- this is the kind of research taste I want to build a lab around

### Slide: 2025 AGI Course As Benchmark Design

- can an agent infer the governing rule of a tweaked MDP
- can it adapt a known tactic to an unseen map within an interaction budget
- this was meant to wake students up from architecture-first thinking

### Slide: Homework 1 To Homework 2

- hw1: solve a known map well
- hw2: survive unseen maps, new obstacles, and possible rule variation
- submit code, use 60 seconds of exploration, then design a tactic

### Slide: Why This Felt Aligned With ARC-AGI-3 Preview

- independently built around a similar problem definition
- adaptation and rule inference mattered more than memorized competence
- again, the joy came from seeing directional alignment

### Slide: Two Directions I Am Watching Now

- solve ARC-AGI-3 in a way that touches the real capability bottlenecks
- avoid ad-hoc walkarounds that only game the benchmark
- ask what ARC-AGI-4 should reward in the first place

### Slide: What Should A Next-Generation Benchmark Measure?

- not only competence, but persistence, curiosity, and self-driven exploration
- not only task completion, but the high-level objective shaping behavior
- if we will live with AI, benchmark design becomes a value statement

### 5. Collaboration Shapes

- light-weight brainstorming and rapid prototyping
- small exploratory project with clear milestone
- shared benchmark / evaluation / data curation effort
- longer-horizon research agenda if there is strong fit

### 6. What Would Make This Visit Valuable

- 구체적인 공동 연구 아이디어 하나를 남기는 것
- 바로 시작 가능한 작은 실험 하나를 정의하는 것
- 이후에 자연스럽게 이어질 communication channel을 만드는 것

### 7. Closing

- 오늘 톡은 answer를 주기 위한 자리라기보다, 좋은 next question을 같이 찾기 위한 자리였다.
- 만약 몇 가지 방향이 서로에게 재미있게 느껴진다면, 이 방문은 이미 충분히 가치가 있다.

## Slide Skeleton

1. Title
2. Who I Am / Why I Am Here
3. Why This Is Not a Standard Seminar
4. Research Taste: What Problems I Keep Coming Back To
5. ARC As An Early Example
6. Why Those Questions Mattered
7. 2024 ARC Landscape: Pretraining Versus Test-Time Strategy
8. Our Framing: ARC As Sequential Decision Making
9. Another Framing: ARC As An Abductive Reasoning Problem
10. ARCLE, SOLAR, and LDCQ
11. What I Find Intellectually Rewarding As A PI
12. 2025 AGI Course: Meta-Level Agent and Unknown Maps
13. Why This Felt Aligned With ARC-AGI-3 Preview
14. Two Directions I Am Watching Now
15. What Could Be Interesting to Build Together
16. Possible Collaboration Formats
17. Open Discussion

## Notes For Later Refinement With Claude

- 자기소개 디테일 보강
- pointer 3개를 실제 연구 관심사와 연결
- ARC 논문 figure 또는 augmentation example 넣을 위치 결정
- 2024 ARC landscape 슬라이드에 넣을 winner examples와 citations 정리
- GRPO 연결에 사용할 정확한 citation 확인
- abductive symbolic solver pipeline figure를 어디에 넣을지 결정
- PI 관점을 설명하는 개인적 문장을 좀 더 구어체로 다듬기
- GIF-ARC를 다음 사례로 어떻게 연결할지 정리
- Othello benchmark arXiv citation과 TMLR submission wording 확인
- benchmark overfitting critique에 대응할 citation 후보 정리
- MSRA audience에 맞게 collaboration examples 구체화
- 마무리 문구를 더 자연스럽고 personal하게 다듬기
