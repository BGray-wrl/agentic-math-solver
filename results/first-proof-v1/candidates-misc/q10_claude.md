\documentclass[11pt]{amsart}

\usepackage{amsmath,amssymb,amsthm,mathtools}
\usepackage[margin=1in]{geometry}
\usepackage{algorithm,algpseudocode}

\newtheorem{proposition}{Proposition}
\newtheorem{lemma}[proposition]{Lemma}
\newtheorem{remark}[proposition]{Remark}
\theoremstyle{definition}
\newtheorem{definition}[proposition]{Definition}

\DeclareMathOperator{\vecop}{vec}
\DeclareMathOperator{\diag}{diag}
\newcommand{\R}{\mathbb{R}}
\newcommand{\cT}{\mathcal{T}}
\newcommand{\cA}{\mathcal{A}}
\newcommand{\cP}{\mathcal{P}}

\begin{document}

\title{Efficient solution of the RKHS-constrained mode subproblem in CP
tensor completion via preconditioned conjugate gradients}

\maketitle

\section{Setup}\label{sec:setup}

We adopt the notation and terminology of \cite{KoldaBader2009} for tensor
operations.  Let $\cT \in \R^{n_1 \times \cdots \times n_d}$ be a
partially observed $d$-way tensor, and suppose we seek a rank-$r$
CP decomposition \cite[Definition~3.1]{KoldaBader2009} via alternating
optimization over the factor matrices $A_1,\dots,A_d$.  We consider the
mode-$k$ subproblem in which the factor matrices for all modes $i \neq k$
are fixed and mode~$k$ is constrained to a reproducing kernel Hilbert
space (RKHS) in the sense of Aronszajn \cite{Aronszajn1950}.

Write $n = n_k$, $M = \prod_{i \neq k} n_i$, and $N = nM$.  Let
$T \in \R^{n \times M}$ denote the mode-$k$ unfolding of $\cT$
\cite[Section~2.4]{KoldaBader2009} with unobserved entries set to zero,
and let $q \ll N$ denote the number of observed entries.  Define the
\emph{selection matrix} $S \in \R^{N \times q}$ as the submatrix of
$I_N$ whose columns correspond to the observed entries, so that
$S^T \vecop(T)$ extracts the $q$ known entries.  Let
\[
  Z
  = A_d \odot \cdots \odot A_{k+1} \odot A_{k-1} \odot \cdots \odot A_1
  \in \R^{M \times r}
\]
be the Khatri--Rao product \cite[Section~2.6]{KoldaBader2009} of the
fixed factor matrices, and let $B = TZ \in \R^{n \times r}$ be the
matricized tensor times Khatri--Rao product (MTTKRP)
\cite[Section~3.3]{KoldaBader2009}.

We parameterize the mode-$k$ factor as $A_k = KW$, where $K\in\R^{n\times n}$
is the symmetric positive semi-definite kernel (Gram) matrix
\cite[Section~1]{Aronszajn1950} associated with the RKHS and
$W\in\R^{n\times r}$ is unknown.  The regularized least-squares
subproblem yields the normal equations
\begin{equation}\label{eq:system}
  \cA\,\vecop(W) = \mathbf{b},
\end{equation}
where
\begin{equation}\label{eq:A}
  \cA
  = (Z\otimes K)^T S\,S^T (Z\otimes K) + \lambda\,(I_r\otimes K),
  \qquad
  \mathbf{b}
  = (I_r\otimes K)\,\vecop(B),
\end{equation}
and $\lambda > 0$ is a regularization parameter.  System~\eqref{eq:system}
has dimension $nr \times nr$.  A direct factorization costs
$O(n^3 r^3)$ and requires explicit formation of $\cA$; we show that
preconditioned conjugate gradients (PCG) achieves per-iteration cost
$O(qr + n^2 r + nr^2)$ with no computation of order~$N$.

%----------------------------------------------------------------------
\section{Properties of the system}\label{sec:properties}
%----------------------------------------------------------------------

\begin{lemma}\label{lem:spd}
  The matrix $\cA$ defined in~\eqref{eq:A} is symmetric positive
  semi-definite.  If $K$ is positive definite, then $\cA$ is positive
  definite.
\end{lemma}

\begin{proof}
Write $\cA = C^T C + \lambda\,(I_r \otimes K)$ where
$C = S^T(Z \otimes K)$.  The first summand $C^T C$ is symmetric
positive semi-definite, and $I_r \otimes K$ is positive semi-definite
since $K$ is.  When $K \succ 0$, the second summand $\lambda(I_r\otimes K)
\succ 0$, so $\cA\succ 0$.
\end{proof}

Since $\cA$ is symmetric positive definite (assuming $K\succ 0$), the
conjugate gradient method \cite{HestenesStiefel1952} is applicable and
converges in at most $nr$ iterations.

%----------------------------------------------------------------------
\section{Efficient matrix--vector products}\label{sec:matvec}
%----------------------------------------------------------------------

The central tool is the following standard identity for Kronecker products
and the $\vecop$ operator.

\begin{lemma}[{cf.\ \cite[Theorem~4.2.10]{HornJohnson1991}}]
  \label{lem:vec}
  For matrices $A \in \R^{m\times n}$, $X \in \R^{n \times p}$,
  $B \in \R^{p \times s}$, one has
  \[
    (B^T \otimes A)\,\vecop(X) = \vecop(AXB).
  \]
\end{lemma}

\begin{proposition}\label{prop:matvec}
  Given $W \in \R^{n \times r}$, the product
  $\cA\,\vecop(W)$ can be evaluated in $O(qr + n^2 r)$ operations
  without forming or storing any object of dimension~$N$.
\end{proposition}

\begin{proof}
  We decompose the computation into three stages.

  \medskip\noindent\textbf{Stage 1: Forward map.}
  By Lemma~\ref{lem:vec} with $A=K$, $X=W$, $B=Z^T$,
  \begin{equation}\label{eq:forward}
    (Z \otimes K)\,\vecop(W) = \vecop(K W Z^T).
  \end{equation}
  Forming the $n \times M$ matrix $KWZ^T$ explicitly would cost $O(nMr)$,
  which is of order~$N$.  Instead, we first compute
  $P = KW \in \R^{n \times r}$ at cost $O(n^2 r)$ and then evaluate only
  the $q$ entries selected by $S^T$.  Each observed entry is indexed by a
  pair $(i_s, j_s) \in \{1,\dots,n\}\times\{1,\dots,M\}$ for
  $s=1,\dots,q$, and
  \begin{equation}\label{eq:ys}
    y_s
    = (KWZ^T)_{i_s, j_s}
    = \sum_{\ell=1}^{r} P_{i_s,\ell}\, Z_{j_s,\ell},
  \end{equation}
  which requires $O(r)$ operations per entry and $O(qr)$ in total.
  Thus $y = S^T(Z\otimes K)\,\vecop(W) \in \R^q$ is obtained in
  $O(n^2 r + qr)$ operations without forming any $N$-dimensional quantity.

  \medskip\noindent\textbf{Stage 2: Adjoint map.}
  We require $(Z\otimes K)^T S\,y = (Z^T\otimes K)\,Sy$.
  The vector $Sy \in \R^N$ has at most $q$ nonzero entries;
  its mode-$k$ matricization $V\in\R^{n\times M}$ satisfies
  $V_{i_s,j_s} = y_s$ for $s=1,\dots,q$ and is zero elsewhere.
  By Lemma~\ref{lem:vec} with $A=K$, $X=V$, $B^T = Z^T$ (i.e., $B=Z$),
  \begin{equation}\label{eq:adjoint}
    (Z^T \otimes K)\,\vecop(V)
    = \vecop(KVZ).
  \end{equation}
  Since $V$ has only $q$ nonzero entries, the product $G = VZ \in\R^{n\times r}$
  is computed by the scatter operation
  \[
    G_{i,\ell} = \sum_{\substack{s=1,\dots,q \\ i_s = i}} y_s\, Z_{j_s,\ell},
    \qquad i=1,\dots,n,\quad \ell=1,\dots,r,
  \]
  at cost $O(qr)$.  Subsequently, $KG$ costs $O(n^2 r)$.  This stage
  therefore costs $O(qr + n^2 r)$.

  \medskip\noindent\textbf{Stage 3: Regularization.}
  By Lemma~\ref{lem:vec}, $\lambda(I_r \otimes K)\,\vecop(W)
  = \lambda\,\vecop(KW) = \lambda\,\vecop(P)$.  The matrix $P=KW$ was
  already computed in Stage~1, so no additional work is required.

  \medskip\noindent\textbf{Assembly.}
  Combining Stages~1--3,
  \begin{equation}\label{eq:fullmatvec}
    \cA\,\vecop(W) = \vecop(KG + \lambda P).
  \end{equation}
  The total cost is $O(qr + n^2 r)$, dominated by the sparse inner
  products~\eqref{eq:ys} and the dense matrix multiplications with~$K$.
  At no point is an $N$-dimensional vector or $n\times M$ dense matrix
  formed.
\end{proof}

\begin{remark}\label{rem:rhs}
  The right-hand side $\mathbf{b} = \vecop(KB)$ requires the MTTKRP
  $B = TZ \in \R^{n \times r}$, which costs $O(qr)$ since the mode-$k$
  unfolding~$T$ has exactly $q$ nonzero entries
  \cite[Section~3.3]{KoldaBader2009}, followed by a multiplication with
  $K$ at cost $O(n^2 r)$.
\end{remark}

%----------------------------------------------------------------------
\section{Preconditioner}\label{sec:precond}
%----------------------------------------------------------------------

The diagonal matrix $\Omega = SS^T \in \R^{N \times N}$ has
$\Omega_{ii} = 1$ if entry $i$ is observed and $\Omega_{ii}=0$ otherwise.
For the purpose of constructing a spectrally faithful preconditioner with
exploitable Kronecker structure, we replace $\Omega$ by the scalar
matrix $\frac{q}{N}\,I_N$.  This substitution is justified by the
following elementary observation.

\begin{lemma}\label{lem:sampling}
  If the index set of observed entries is drawn uniformly at random
  with inclusion probability $p = q/N$ per entry, then
  $\mathbb{E}[\Omega] = p\,I_N$.
\end{lemma}

\begin{proof}
  Each diagonal entry $\Omega_{ii}$ is an independent Bernoulli random
  variable with parameter~$p$.
\end{proof}

Replacing $\Omega$ by its expectation in~\eqref{eq:A}, we define
\begin{equation}\label{eq:precond}
  \cP
  = \frac{q}{N}\,(Z \otimes K)^T (Z \otimes K)
  + \lambda\,(I_r \otimes K)
  = \frac{q}{N}\,(Z^T Z \otimes K^2)
  + \lambda\,(I_r \otimes K),
\end{equation}
where the second equality uses the mixed-product property of Kronecker
products \cite[Theorem~4.2.10]{HornJohnson1991} together with the
symmetry $K^T = K$.

\begin{proposition}\label{prop:precond}
  After a one-time setup of cost $O(n^3 + r^3)$, linear systems of the
  form $\cP\,\vecop(X) = \vecop(F)$ can be solved in
  $O(n^2 r + nr^2)$ operations.
\end{proposition}

\begin{proof}
  Compute the eigendecompositions
  \[
    K = U \Sigma U^T, \qquad
    Z^T Z = V \Lambda V^T,
  \]
  where $U \in \R^{n \times n}$ and $V \in \R^{r \times r}$ are
  orthogonal, $\Sigma = \diag(\sigma_1,\dots,\sigma_n)$, and
  $\Lambda = \diag(\mu_1,\dots,\mu_r)$.  These decompositions cost
  $O(n^3)$ and $O(r^3)$, respectively
  \cite[Section~8.1]{GolubVanLoan2013}.  Substituting into~\eqref{eq:precond},
  \[
    \cP
    = (V \otimes U)
    \left[
      \frac{q}{N}\,(\Lambda \otimes \Sigma^2)
      + \lambda\,(I_r \otimes \Sigma)
    \right]
    (V^T \otimes U^T).
  \]
  The bracketed matrix is diagonal with entries
  \begin{equation}\label{eq:diag_entries}
    d_{j,i}
    = \frac{q}{N}\,\mu_j\,\sigma_i^2 + \lambda\,\sigma_i,
    \qquad j=1,\dots,r,\quad i=1,\dots,n.
  \end{equation}
  Each $d_{j,i} > 0$ provided $K \succ 0$ and $\lambda > 0$, since
  $\sigma_i > 0$ and $\mu_j \geq 0$.

  Given $F \in \R^{n \times r}$, solve $\cP\,\vecop(X) = \vecop(F)$ as
  follows.
  \begin{enumerate}
    \item Compute $\hat{F} = U^T F V \in \R^{n \times r}$.
      By Lemma~\ref{lem:vec}, this effects the change of basis
      $(V^T \otimes U^T)\,\vecop(F) = \vecop(U^T F V)$.
      \textit{Cost:} $O(n^2 r + nr^2)$.
    \item Set $\hat{X}_{i,j} = \hat{F}_{i,j} / d_{j,i}$ for all $i,j$.
      \textit{Cost:} $O(nr)$.
    \item Compute $X = U \hat{X} V^T$.
      \textit{Cost:} $O(n^2 r + nr^2)$.
  \end{enumerate}
  The total solve cost is $O(n^2 r + nr^2)$.
\end{proof}

%----------------------------------------------------------------------
\section{Preconditioned conjugate gradient algorithm}\label{sec:pcg}
%----------------------------------------------------------------------

We apply the standard PCG iteration
\cite{HestenesStiefel1952,GolubVanLoan2013} to
system~\eqref{eq:system} with preconditioner~$\cP$.  The full procedure
is recorded in Algorithm~\ref{alg:pcg} for completeness.

\begin{algorithm}[ht]
\caption{PCG for the RKHS mode-$k$ subproblem~\eqref{eq:system}}
\label{alg:pcg}
\begin{algorithmic}[1]
  \Require Kernel matrix $K$, Khatri--Rao product $Z$, MTTKRP $B$,
  observation indices $\{(i_s,j_s)\}_{s=1}^q$, regularization $\lambda>0$, tolerance $\varepsilon>0$
  \Ensure Approximate solution $W\in\R^{n\times r}$
  \State \textbf{Precompute:} $U,\Sigma \gets \text{eig}(K)$;\;
         $V,\Lambda \gets \text{eig}(Z^TZ)$;\;
         diagonal~\eqref{eq:diag_entries}
  \State $\mathbf{b} \gets \vecop(KB)$
  \State $W_0 \gets 0$;\; $\mathbf{r}_0 \gets \mathbf{b}$
  \State $\mathbf{z}_0 \gets \cP^{-1}\mathbf{r}_0$
         \Comment{Proposition~\ref{prop:precond}}
  \State $\mathbf{p}_0 \gets \mathbf{z}_0$
  \For{$t = 0, 1, 2, \dots$}
    \State $\mathbf{v} \gets \cA\,\mathbf{p}_t$
           \Comment{Proposition~\ref{prop:matvec}}
    \State $\alpha_t \gets
           \mathbf{r}_t^T \mathbf{z}_t \,/\,
           \mathbf{p}_t^T \mathbf{v}$
    \State $\mathbf{w}_{t+1} \gets \mathbf{w}_t + \alpha_t\,\mathbf{p}_t$
    \State $\mathbf{r}_{t+1} \gets \mathbf{r}_t - \alpha_t\,\mathbf{v}$
    \If{$\|\mathbf{r}_{t+1}\| < \varepsilon\,\|\mathbf{b}\|$}
      \textbf{return} $W_{t+1}$ (reshaped from $\mathbf{w}_{t+1}$)
    \EndIf
    \State $\mathbf{z}_{t+1} \gets \cP^{-1}\mathbf{r}_{t+1}$
    \State $\beta_t \gets
           \mathbf{r}_{t+1}^T \mathbf{z}_{t+1} \,/\,
           \mathbf{r}_t^T \mathbf{z}_t$
    \State $\mathbf{p}_{t+1} \gets \mathbf{z}_{t+1}
           + \beta_t\,\mathbf{p}_t$
  \EndFor
\end{algorithmic}
\end{algorithm}

%----------------------------------------------------------------------
\section{Complexity analysis}\label{sec:complexity}
%----------------------------------------------------------------------

\begin{proposition}\label{prop:complexity}
  Suppose $K\succ 0$ and $\lambda > 0$.
  Algorithm~\ref{alg:pcg} has the following operation counts:
  \begin{enumerate}
    \item[\textup{(i)}] \textbf{One-time preprocessing:} $O(n^3 + r^3)$
      for the eigendecompositions of $K$ and $Z^TZ$, plus $O(qr + n^2r)$
      for the MTTKRP and right-hand side.
    \item[\textup{(ii)}] \textbf{Per iteration:}
      $O(qr + n^2 r + nr^2)$ for one matrix--vector product with $\cA$
      \textup{(}Proposition~\textup{\ref{prop:matvec})} and one
      preconditioner solve with~$\cP$
      \textup{(}Proposition~\textup{\ref{prop:precond})}, together with
      $O(nr)$ for vector updates and inner products.
    \item[\textup{(iii)}] \textbf{Total after $t$ iterations:}
      $O(n^3 + r^3 + t(qr + n^2 r + nr^2))$.
  \end{enumerate}
  Under the assumption $n, r \ll q$, the dominant per-iteration cost
  simplifies to $O(qr)$.  No computation of order~$N$ is performed.
\end{proposition}

\begin{proof}
  Claim~(i) follows from Proposition~\ref{prop:precond} (eigendecompositions)
  and Remark~\ref{rem:rhs} (right-hand side).  Claim~(ii) combines
  Propositions~\ref{prop:matvec} and~\ref{prop:precond} with the
  observation that each CG iteration requires exactly one product
  with~$\cA$, one solve with~$\cP$, and a constant number of
  $\R^{nr}$-vector operations \cite[Algorithm~11.5.1]{GolubVanLoan2013}.
  Claim~(iii) follows by summation.  Since $n^2 r \leq qr$ and
  $nr^2 \leq qr$ when $n,r \leq q^{1/2}$ (which is implied by
  $n,r \ll q$), the per-iteration cost is $O(qr)$.

  To verify the absence of $O(N)$ work: all multiplications with $K$ or
  $K^2$ involve matrices of size $n\times n$; products with $Z$ or
  $Z^TZ$ are either scatter operations over $q$ entries or involve the
  $r\times r$ matrix $Z^TZ$; and the selection operator $S$ is applied
  only through pointwise evaluation at the $q$ observed indices
  \eqref{eq:ys} or through the sparse scatter of Stage~2 in the proof
  of Proposition~\ref{prop:matvec}.
\end{proof}

\begin{remark}\label{rem:convergence}
  The convergence rate of PCG is governed by the condition number
  $\kappa(\cP^{-1}\cA)$
  \cite[Theorem~11.3.3]{GolubVanLoan2013}: after $t$~iterations,
  \[
    \|\mathbf{w}_t - \mathbf{w}_*\|_{\cA}
    \leq
    2\left(
      \frac{\sqrt{\kappa(\cP^{-1}\cA)} - 1}
           {\sqrt{\kappa(\cP^{-1}\cA)} + 1}
    \right)^{\!t}
    \|\mathbf{w}_0 - \mathbf{w}_*\|_{\cA}.
  \]
  Since the preconditioner $\cP$ is obtained from $\cA$ by replacing
  $\Omega = SS^T$ with $\frac{q}{N}I_N$
  (Lemma~\ref{lem:sampling}), $\kappa(\cP^{-1}\cA)$ is controlled by
  the deviation of the sampling operator from its expectation.  When the
  observation pattern is close to uniform, $\cP^{-1}\cA$ is
  well-conditioned and a small number of iterations suffices.
\end{remark}

\begin{remark}\label{rem:comparison}
  Forming the $nr\times nr$ system matrix $\cA$ explicitly requires
  $O(qn r + n^2 r^2)$ operations, and solving via Cholesky factorization
  costs $O(n^3 r^3)$ \cite[Section~4.2]{GolubVanLoan2013}.
  Algorithm~\ref{alg:pcg} is therefore advantageous whenever the number
  of PCG iterations $t$ satisfies $t \ll n^2 r^2 / q$, a condition that
  is easily met in practice.
\end{remark}

%----------------------------------------------------------------------
\begin{thebibliography}{10}

\bibitem{Aronszajn1950}
N.~Aronszajn,
\emph{Theory of reproducing kernels},
Trans.\ Amer.\ Math.\ Soc.\ \textbf{68} (1950), 337--404.

\bibitem{GolubVanLoan2013}
G.~H.~Golub and C.~F.~Van~Loan,
\emph{Matrix Computations},
4th ed., Johns Hopkins Univ.\ Press, Baltimore, 2013.

\bibitem{HestenesStiefel1952}
M.~R.~Hestenes and E.~Stiefel,
\emph{Methods of conjugate gradients for solving linear systems},
J.~Research Nat.\ Bur.\ Standards \textbf{49} (1952), no.~6, 409--436.

\bibitem{HornJohnson1991}
R.~A.~Horn and C.~R.~Johnson,
\emph{Topics in Matrix Analysis},
Cambridge Univ.\ Press, Cambridge, 1991.

\bibitem{KoldaBader2009}
T.~G.~Kolda and B.~W.~Bader,
\emph{Tensor decompositions and applications},
SIAM Rev.\ \textbf{51} (2009), no.~3, 455--500.

\end{thebibliography}

\end{document}
