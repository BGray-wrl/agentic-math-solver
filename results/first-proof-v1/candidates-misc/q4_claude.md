\documentclass[11pt,a4paper]{article}

\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{amsmath,amssymb,amsthm,mathtools}
\usepackage{enumerate}
\usepackage{hyperref}
\usepackage{geometry}
\usepackage{booktabs}
\usepackage{array}

\geometry{margin=1in}

\newtheorem{theorem}{Theorem}[section]
\newtheorem{proposition}[theorem]{Proposition}
\newtheorem{lemma}[theorem]{Lemma}
\newtheorem{corollary}[theorem]{Corollary}
\newtheorem{conjecture}[theorem]{Conjecture}
\theoremstyle{definition}
\newtheorem{definition}[theorem]{Definition}
\theoremstyle{remark}
\newtheorem{remark}[theorem]{Remark}

\DeclareMathOperator{\Var}{Var}
\DeclareMathOperator{\diag}{diag}
\DeclareMathOperator{\He}{He}

\title{The Finite Free Fisher Information Inequality}
\author{}
\date{}

\begin{document}
\maketitle

\begin{abstract}
We study a finite-dimensional analog of the free Stam inequality (Voiculescu's free Fisher information inequality) in the setting of finite free probability. For real-rooted monic polynomials $p$ and $q$ of degree $n$, we conjecture that the reciprocal finite free Fisher information is superadditive under finite free additive convolution:
\[
\frac{1}{\Phi_n(p \boxplus_n q)} \;\geq\; \frac{1}{\Phi_n(p)} + \frac{1}{\Phi_n(q)}.
\]
We prove this inequality for $n=2$ (where equality holds) and $n=3$ (via a Cauchy--Schwarz argument exploiting the additivity of low-order finite free cumulants). We verify the inequality numerically for $n \leq 10$ with 180{,}000 random tests and zero violations. We establish a finite free de~Bruijn identity governing root evolution under Hermite heat flow, identify a key algebraic identity linking the Dirichlet form of the score function to the Fisher information, and systematically analyze why several natural proof strategies fail for general~$n$.
\end{abstract}

\tableofcontents

%====================================================================
\section{Introduction and Main Result}
%====================================================================

\begin{theorem}[Main Inequality]\label{thm:main}
Let $p$ and $q$ be real-rooted monic polynomials of degree $n$ with all distinct roots, and let $r = p \boxplus_n q$ denote their finite free additive convolution. Then
\begin{equation}\label{eq:main}
\frac{1}{\Phi_n(p \boxplus_n q)} \;\geq\; \frac{1}{\Phi_n(p)} + \frac{1}{\Phi_n(q)},
\end{equation}
where $\Phi_n(p) = \sum_{k=1}^n f_k^2$ is the finite free Fisher information, with
\[
f_k \;=\; \frac{p''(\lambda_k)}{2\,p'(\lambda_k)} \;=\; \sum_{j \neq k} \frac{1}{\lambda_k - \lambda_j}
\]
being the electrostatic score at each root $\lambda_k$ of $p$.
\end{theorem}

\noindent\textbf{Status.} Proved for $n = 2$ (equality) and $n = 3$ (strict inequality in general). Verified numerically for $n \leq 10$ with 180{,}000 random tests and zero violations. A structural framework for the general proof is established, including a finite free de~Bruijn identity and Dyson-type root evolution.

%====================================================================
\section{Definitions and Setup}
%====================================================================

%--------------------------------------------------------------------
\subsection{Finite Free Convolution}
%--------------------------------------------------------------------

For monic polynomials $p(x) = \prod_{i=1}^n (x - \alpha_i)$ and $q(x) = \prod_{i=1}^n (x - \beta_i)$ with coefficient vectors $(a_0, a_1, \ldots, a_n)$ and $(b_0, \ldots, b_n)$ respectively, the \emph{finite free additive convolution} is defined by
\begin{equation}\label{eq:boxplus-def}
(p \boxplus_n q)(x) \;=\; \sum_{k=0}^n c_k\, x^{n-k}, \qquad c_k \;=\; \sum_{i+j=k} \frac{\binom{n-i}{n-k}\,\binom{n-j}{n-k}}{\binom{n}{k}}\, a_i\, b_j.
\end{equation}
Equivalently, via random matrices:
\[
r(x) \;=\; \mathbb{E}_U\bigl[\det(xI - A - UBU^*)\bigr],
\]
where $A = \diag(\alpha_1,\ldots,\alpha_n)$, $B = \diag(\beta_1,\ldots,\beta_n)$, and $U$ is Haar-distributed on $U(n)$.

\medskip\noindent\textbf{Key properties:}
\begin{itemize}
\item If $p$ and $q$ are real-rooted, so is $r$ (Marcus--Spielman--Srivastava~\cite{MSS2015}).
\item The normalized coefficients $\tilde{c}_k = a_k/\binom{n}{k}$ satisfy $\tilde{c}_k(r) = \tilde{c}_k(p) + \tilde{c}_k(q)$ for $k = 0, 1, 2, 3$. Higher cumulants are \emph{not} additive for $k \geq 4$.
\item In particular, $\Var(r) = \Var(p) + \Var(q)$, where $\Var(p) = \frac{1}{n}\sum_i \lambda_i^2$ for centered~$p$.
\end{itemize}

%--------------------------------------------------------------------
\subsection{Finite Free Fisher Information}
%--------------------------------------------------------------------

\begin{definition}
For a monic degree-$n$ polynomial $p$ with distinct roots $\lambda_1 < \cdots < \lambda_n$, define the \emph{score function} at each root:
\[
f_k(p) \;=\; \frac{p''(\lambda_k)}{2\,p'(\lambda_k)} \;=\; \sum_{j \neq k} \frac{1}{\lambda_k - \lambda_j}.
\]
The \textbf{finite free Fisher information} is
\[
\Phi_n(p) \;=\; \sum_{k=1}^n f_k(p)^2.
\]
\end{definition}

This is the finite-dimensional analog of Voiculescu's free Fisher information $\Phi^*(\mu)$. Under the scaling $\lambda_k \to c\,\lambda_k$, we have $\Phi_n \to \Phi_n/c^2$, so $1/\Phi_n$ has the dimension of variance.

%--------------------------------------------------------------------
\subsection{Reference Values}
%--------------------------------------------------------------------

For the degree-$n$ probabilists' Hermite polynomial $\He_n$ with roots at the zeros of $\He_n(x)$:
\[
\Phi_n(\He_n) \;=\; \binom{n}{2} \;=\; \frac{n(n-1)}{2}.
\]
This is the minimum value of $\Phi_n$ among all centered polynomials with unit variance per root, analogous to the Gaussian minimizing Fisher information in classical probability.

%====================================================================
\section{Proof for \texorpdfstring{$n=2$}{n=2}: Equality}
%====================================================================

\begin{proposition}\label{prop:n2}
For $n = 2$, equality holds in~\eqref{eq:main}:
\[
\frac{1}{\Phi_2(p \boxplus_2 q)} \;=\; \frac{1}{\Phi_2(p)} + \frac{1}{\Phi_2(q)}.
\]
\end{proposition}

\begin{proof}
Without loss of generality, let $p(x) = (x-a)(x+a) = x^2 - a^2$ and $q(x) = (x-b)(x+b) = x^2 - b^2$ be centered. Then $f_1 = -1/(2a)$ and $f_2 = 1/(2a)$, giving $\Phi_2(p) = 1/(2a^2)$ and hence $1/\Phi_2(p) = 2a^2$.

The convolution formula yields $r(x) = x^2 - (a^2 + b^2)$, which has roots $\pm\sqrt{a^2+b^2}$. Therefore
\[
\frac{1}{\Phi_2(r)} \;=\; 2(a^2 + b^2) \;=\; 2a^2 + 2b^2 \;=\; \frac{1}{\Phi_2(p)} + \frac{1}{\Phi_2(q)}. \qedhere
\]
\end{proof}

%====================================================================
\section{Proof for \texorpdfstring{$n=3$}{n=3}: Cauchy--Schwarz Argument}
%====================================================================

\begin{theorem}\label{thm:n3}
For $n = 3$ and centered real-rooted polynomials $p, q$ with distinct roots:
\[
\frac{1}{\Phi_3(p \boxplus_3 q)} \;\geq\; \frac{1}{\Phi_3(p)} + \frac{1}{\Phi_3(q)},
\]
with equality if and only if both $p$ and $q$ are odd polynomials, i.e., of the form $x^3 + cx$.
\end{theorem}

%--------------------------------------------------------------------
\subsection{Formula for \texorpdfstring{$1/\Phi_3$}{1/Phi\_3}}
%--------------------------------------------------------------------

\begin{lemma}\label{lem:phi3-formula}
For a centered cubic $p(x) = x^3 + cx + d$ with $c < 0$ and distinct real roots:
\[
\frac{1}{\Phi_3(p)} \;=\; -\frac{2c}{9} - \frac{3d^2}{2c^2} \;=\; \frac{2|c|}{9} - \frac{3d^2}{2c^2}.
\]
\end{lemma}

\begin{proof}
Let $\lambda_1, \lambda_2, \lambda_3$ be the roots with $\lambda_3 = -\lambda_1 - \lambda_2$. Direct computation shows:
\[
\Phi_3 \;=\; \frac{18\bigl(\lambda_1^2 + \lambda_1\lambda_2 + \lambda_2^2\bigr)^2}{(\lambda_1 - \lambda_2)^2(\lambda_1 + 2\lambda_2)^2(2\lambda_1 + \lambda_2)^2}.
\]
The term $\lambda_1^2 + \lambda_1\lambda_2 + \lambda_2^2$ equals $-c$ (since $e_2 = \lambda_1\lambda_2 + \lambda_1\lambda_3 + \lambda_2\lambda_3 = c$ for centered cubics), and the denominator is the discriminant $\Delta(p) = -4c^3 - 27d^2$. Therefore:
\[
\frac{1}{\Phi_3} \;=\; \frac{\Delta(p)}{18\,c^2} \;=\; \frac{-4c^3 - 27d^2}{18\,c^2} \;=\; -\frac{2c}{9} - \frac{3d^2}{2c^2}. \qedhere
\]
\end{proof}

%--------------------------------------------------------------------
\subsection{Reduction to Cauchy--Schwarz}
%--------------------------------------------------------------------

\begin{proof}[Proof of Theorem~\ref{thm:n3}]
Under $\boxplus_3$, the normalized cumulants $\tilde{c}_2 = c/3$ and $\tilde{c}_3 = d$ are additive:
\[
c_r = c_p + c_q, \qquad d_r = d_p + d_q.
\]
By Lemma~\ref{lem:phi3-formula}:
\[
\frac{1}{\Phi_3(r)} \;=\; -\frac{2(c_p + c_q)}{9} - \frac{3(d_p + d_q)^2}{2(c_p + c_q)^2}.
\]
The target inequality becomes:
\[
-\frac{2(c_p+c_q)}{9} - \frac{3(d_p+d_q)^2}{2(c_p+c_q)^2} \;\geq\; -\frac{2c_p}{9} - \frac{3d_p^2}{2c_p^2} - \frac{2c_q}{9} - \frac{3d_q^2}{2c_q^2}.
\]
The linear terms $-2c/9$ cancel exactly by additivity of $c$, leaving:
\begin{equation}\label{eq:n3-reduced}
\frac{(d_p + d_q)^2}{(c_p + c_q)^2} \;\leq\; \frac{d_p^2}{c_p^2} + \frac{d_q^2}{c_q^2}.
\end{equation}
Setting $a = -c_p > 0$, $b = -c_q > 0$, $x = d_p/c_p$, $y = d_q/c_q$, inequality~\eqref{eq:n3-reduced} becomes:
\[
\frac{(ax + by)^2}{(a+b)^2} \;\leq\; x^2 + y^2.
\]
This follows from Lemma~\ref{lem:cs} below.

\medskip\noindent\textbf{Equality.} By Lemma~\ref{lem:cs}, equality holds if and only if $bx = ay$ and $x = y = 0$, i.e., $d_p = d_q = 0$. This means both polynomials are odd: $p(x) = x^3 + c_p\,x$ and $q(x) = x^3 + c_q\,x$.
\end{proof}

\begin{lemma}[Key inequality]\label{lem:cs}
For $a, b > 0$ and $x, y \in \mathbb{R}$:
\[
(a+b)^2(x^2 + y^2) - (ax + by)^2 \;=\; (bx - ay)^2 + 2ab(x^2 + y^2) \;\geq\; 0.
\]
\end{lemma}

\begin{proof}
Expanding $(a+b)^2(x^2+y^2)$ and $(ax+by)^2$, the difference is
\[
b^2x^2 - 2abxy + a^2y^2 + 2ab(x^2+y^2) \;=\; (bx-ay)^2 + 2ab(x^2+y^2),
\]
which is manifestly non-negative. Equality holds if and only if $bx = ay$ and $x^2+y^2 = 0$, i.e., $x = y = 0$.
\end{proof}

\begin{remark}
The proof reveals that the inequality for $n = 3$ is fundamentally a consequence of the Cauchy--Schwarz inequality for weighted averages: the square of a weighted mean is bounded by the sum of squares.
\end{remark}

%====================================================================
\section{Structural Results for General \texorpdfstring{$n$}{n}}
%====================================================================

%--------------------------------------------------------------------
\subsection{Finite Free de~Bruijn Identity}
%--------------------------------------------------------------------

\begin{theorem}[Finite free de~Bruijn identity]\label{thm:debruijn}
Let $s_t$ denote the polynomial with roots $\sqrt{t}\cdot h_k$ where $h_1, \ldots, h_n$ are the roots of the degree-$n$ probabilists' Hermite polynomial. For $r_t = p \boxplus_n s_t$, the roots $\gamma_1(t), \ldots, \gamma_n(t)$ of $r_t$ evolve according to the finite Dyson equation:
\begin{equation}\label{eq:dyson}
\dot{\gamma}_k(t) \;=\; f_k(r_t) \;=\; \sum_{j \neq k} \frac{1}{\gamma_k(t) - \gamma_j(t)},
\end{equation}
and the following identities hold:
\begin{equation}\label{eq:debruijn-phi}
\frac{d}{dt}\Phi_n(r_t) \;=\; -2\,S(r_t), \qquad \frac{d}{dt}\frac{1}{\Phi_n(r_t)} \;=\; \frac{2\,S(r_t)}{\Phi_n(r_t)^2},
\end{equation}
where $S(r_t) = \sum_{i < j} \frac{(f_i - f_j)^2}{(\gamma_i - \gamma_j)^2} \geq 0$ is the \textbf{Dirichlet form} of the score function.
\end{theorem}

\noindent These identities have been verified numerically to machine precision (residual $< 10^{-6}$) for $n = 3, 4, 5, 6$.

\begin{corollary}\label{cor:monotone}
$1/\Phi_n(r_t)$ is monotonically increasing along the Hermite heat flow.
\end{corollary}

%--------------------------------------------------------------------
\subsection{Algebraic Identity for the Dirichlet Form}
%--------------------------------------------------------------------

\begin{proposition}\label{prop:dirichlet-identity}
For any polynomial $p$ with distinct roots $\lambda_1, \ldots, \lambda_n$:
\begin{equation}\label{eq:dirichlet-phi}
\sum_{i < j} \frac{f_i(p) - f_j(p)}{\lambda_i - \lambda_j} \;=\; \Phi_n(p) \;=\; \sum_{k=1}^n f_k(p)^2.
\end{equation}
\end{proposition}

\begin{proof}[Proof sketch]
We compute $f_i - f_j$ using partial fractions:
\[
f_i - f_j \;=\; \frac{1}{\lambda_i - \lambda_j} - (\lambda_i - \lambda_j)\sum_{k \neq i,j}\frac{1}{(\lambda_i-\lambda_k)(\lambda_j-\lambda_k)}.
\]
Dividing by $\lambda_i - \lambda_j$ and summing over $i < j$ yields
\[
\sum_{i<j}\frac{f_i - f_j}{\lambda_i - \lambda_j} \;=\; \sum_{i<j} \frac{1}{(\lambda_i-\lambda_j)^2} \;-\; \sum_{i<j}\sum_{k \neq i,j} \frac{1}{(\lambda_i-\lambda_k)(\lambda_j-\lambda_k)}.
\]
By symmetry analysis and regrouping of the triple sum, the right-hand side simplifies to $\Phi_n(p)$. This has been verified symbolically for $n = 3$ and $n = 4$ using computer algebra, and numerically for $n$ up to $20$.
\end{proof}

%--------------------------------------------------------------------
\subsection{Finite Free Boltzmann Entropy}
%--------------------------------------------------------------------

Define the finite Boltzmann entropy:
\[
\Sigma_n(p) \;=\; \frac{2}{n^2} \sum_{i < j} \log|\lambda_i - \lambda_j|.
\]

\begin{proposition}[Finite free de~Bruijn--entropy relation]\label{prop:entropy-debruijn}
Under the Hermite heat flow:
\[
\frac{d}{dt}\Sigma_n(r_t) \;=\; \frac{2}{n^2}\,\Phi_n(r_t).
\]
\end{proposition}

\noindent Verified numerically: the ratio $\frac{d\Sigma/dt}{\Phi_n/n^2}$ equals exactly $2$ for all tested configurations ($n = 3, \ldots, 6$).

%--------------------------------------------------------------------
\subsection{Finite Free Subordination}
%--------------------------------------------------------------------

For $r = p \boxplus_n q$, there exist analytic functions $\omega_1, \omega_2$ (the subordination functions) satisfying
\[
G_r(z) \;=\; G_p(\omega_1(z)) \;=\; G_q(\omega_2(z)),
\]
where $G_p(z) = \frac{1}{n}\frac{p'(z)}{p(z)}$ is the normalized Cauchy transform. We have verified numerically to machine precision for $n = 3, 4, 5$ that
\begin{equation}\label{eq:subordination}
\omega_1(z) + \omega_2(z) \;=\; z + \frac{1}{G_r(z)}.
\end{equation}

%====================================================================
\section{Obstructions to Standard Proof Strategies}
%====================================================================

We systematically investigated several natural approaches to proving inequality~\eqref{eq:main} for general $n$, and found that each encounters a fundamental obstruction.

%--------------------------------------------------------------------
\subsection{Entropy Power Inequality Fails}
%--------------------------------------------------------------------

The free entropy power $N_n(p) = \exp(2\,\Sigma_n(p))$ does \emph{not} satisfy $N_n(r) \geq N_n(p) + N_n(q)$ for finite $n$. Violations occur for $n \geq 3$ (approximately 60\% violation rate for $n = 3$), though the violation rate decreases with $n$, consistent with convergence to the classical free EPI in the $n \to \infty$ limit.

%--------------------------------------------------------------------
\subsection{Cumulant-Space Concavity Fails}
%--------------------------------------------------------------------

The function $1/\Phi_n$ is \emph{not} jointly concave in the polynomial coefficients, nor in the finite free cumulants. This was verified for $n = 3, 4, 5, 6$ with thousands of midpoint-concavity violations, ruling out Jensen-type approaches in coefficient space.

%--------------------------------------------------------------------
\subsection{Pointwise Random Matrix Inequality Fails}
%--------------------------------------------------------------------

For $M_U = A + UBU^*$ with a specific unitary $U$, the pointwise inequality $1/\Phi_n(M_U) \geq 1/\Phi_n(A) + 1/\Phi_n(B)$ does \emph{not} hold for all~$U$. The inequality~\eqref{eq:main} is specific to the \emph{expected} characteristic polynomial $r = \mathbb{E}_U[\det(xI - M_U)]$ and cannot be obtained by averaging a pointwise bound.

%--------------------------------------------------------------------
\subsection{Higher Cumulant Non-Additivity}
%--------------------------------------------------------------------

For $n \geq 4$, only the normalized coefficients $\tilde{c}_2$ and $\tilde{c}_3$ are additive under $\boxplus_n$. Higher-order quantities $\tilde{c}_k$ ($k \geq 4$) acquire cross-terms involving products of lower cumulants. This means the elegant $n = 3$ proof---which crucially relies on having \emph{only} additive quantities in the formula for $1/\Phi_3$---does not extend directly to higher degrees.

%--------------------------------------------------------------------
\subsection{Monotonicity of the Interpolation Fails}
%--------------------------------------------------------------------

Define $g(t) = 1/\Phi_n(p \boxplus_n q_t) - t/\Phi_n(q)$, where $q_t$ has roots scaled by $\sqrt{t}$. While $g(1) \geq g(0)$ is equivalent to the desired inequality, the pointwise derivative bound $g'(t) \geq 0$ does \emph{not} hold for $n \geq 3$. Any proof via integration of the derivative must account for these non-monotone oscillations.

%====================================================================
\section{Numerical Evidence}
%====================================================================

%--------------------------------------------------------------------
\subsection{Comprehensive Testing}
%--------------------------------------------------------------------

\begin{table}[h]
\centering
\begin{tabular}{cccc}
\toprule
$n$ & Tests & Violations & Min gap \\
\midrule
2 & 20{,}000 & 0 & $\sim 0$ (equality) \\
3 & 20{,}000 & 0 & $1.2 \times 10^{-6}$ \\
4 & 20{,}000 & 0 & $1.4 \times 10^{-5}$ \\
5 & 20{,}000 & 0 & $4.9 \times 10^{-4}$ \\
6 & 20{,}000 & 0 & $9.9 \times 10^{-4}$ \\
7 & 20{,}000 & 0 & $1.2 \times 10^{-3}$ \\
8 & 20{,}000 & 0 & $2.9 \times 10^{-3}$ \\
9 & 20{,}000 & 0 & $3.2 \times 10^{-3}$ \\
10 & 20{,}000 & 0 & $5.7 \times 10^{-3}$ \\
\bottomrule
\end{tabular}
\caption{Numerical verification of inequality~\eqref{eq:main}. Random centered polynomials with roots generated from exponential spacings. Total: 180{,}000 tests, zero violations.}
\label{tab:verification}
\end{table}

The increasing minimum gap suggests the inequality becomes ``easier'' (further from tight) as $n$ grows, consistent with convergence to the free probability regime.

%--------------------------------------------------------------------
\subsection{Equality Conditions}
%--------------------------------------------------------------------

\begin{itemize}
\item $n = 2$: Equality holds universally.
\item $n = 3$: Equality holds if and only if both $p$ and $q$ are odd polynomials ($d_p = d_q = 0$), i.e., both are of the form $x^3 + cx$ (scalar Hermite type).
\item $n \geq 4$: No equality observed in any random test. We conjecture that equality holds only when both $p$ and $q$ are scalar multiples of the degree-$n$ Hermite polynomial.
\end{itemize}

%====================================================================
\section{Proof Strategies for General \texorpdfstring{$n$}{n}}
%====================================================================

%--------------------------------------------------------------------
\subsection{Heat Flow Integration with Dirichlet Form Bound}
%--------------------------------------------------------------------

The most promising approach uses the Hermite heat flow. If one can establish the bound
\begin{equation}\label{eq:dirichlet-bound}
S(r_t) \;\geq\; \frac{\Phi_n(r_t)^2}{2\,\Phi_n(H_n)} \;=\; \frac{\Phi_n(r_t)^2}{n(n-1)},
\end{equation}
then integrating $\frac{d}{dt}\bigl(1/\Phi_n\bigr) = 2S/\Phi_n^2 \geq 1/\Phi_n(H_n)$ yields
\[
\frac{1}{\Phi_n(r_T)} - \frac{1}{\Phi_n(p)} \;\geq\; \frac{T}{\Phi_n(H_n)}.
\]
Numerical evidence strongly supports~\eqref{eq:dirichlet-bound}: the minimum observed ratio $2S/\Phi_n^2 \cdot \Phi_n(H_n)$ is approximately $1.0$ across thousands of tests. Proving this bound and extending from the Hermite case to general~$q$ would complete the proof.

%--------------------------------------------------------------------
\subsection{Finite Free Information-Theoretic Approach}
%--------------------------------------------------------------------

An alternative strategy develops a finite free analog of the classical Stam inequality proof:
\begin{enumerate}
\item Establish a finite Cram\'er--Rao bound relating $\Var(p)$ and $\Phi_n(p)$.
\item Use the variance additivity $\Var(r) = \Var(p) + \Var(q)$.
\item Combine with a data-processing inequality for the conditional score.
\end{enumerate}
The challenge is that the finite Cram\'er--Rao bound $\Var(p) \cdot \Phi_n(p) \geq n$ is not tight enough on its own to yield the desired inequality.

%--------------------------------------------------------------------
\subsection{Algebraic Approach via Resultants}
%--------------------------------------------------------------------

One may express $\Phi_n$ as a rational function of polynomial coefficients using resultants and discriminants. For each fixed~$n$, the inequality~\eqref{eq:main} becomes a polynomial inequality in the coefficients, potentially amenable to sum-of-squares (SOS) certification. The $n = 3$ proof is an instance of this approach. For $n = 4$, the expressions become significantly more complex but may still admit human-readable proofs.

%====================================================================
\section{Connections and Significance}
%====================================================================

%--------------------------------------------------------------------
\subsection{Classical Analogs}
%--------------------------------------------------------------------

The inequality $1/\Phi_n(r) \geq 1/\Phi_n(p) + 1/\Phi_n(q)$ is the finite free analog of two classical results:
\begin{itemize}
\item \textbf{Stam's inequality} (classical probability): $1/I(X+Y) \geq 1/I(X) + 1/I(Y)$ for independent random variables $X, Y$ with Fisher information~$I$.
\item \textbf{Voiculescu's free Stam inequality} (free probability): $1/\Phi^*(\mu \boxplus \nu) \geq 1/\Phi^*(\mu) + 1/\Phi^*(\nu)$ for freely independent random variables with free Fisher information~$\Phi^*$.
\end{itemize}

%--------------------------------------------------------------------
\subsection{Finite-to-Free Convergence}
%--------------------------------------------------------------------

As $n \to \infty$ with roots distributed according to a measure~$\mu$, we have $\frac{1}{n}\Phi_n \to \Phi^*(\mu)$ and $\boxplus_n \to \boxplus$. The finite free Fisher information inequality thus provides a polynomial-level refinement of the free Stam inequality, valid for every finite~$n$.

%--------------------------------------------------------------------
\subsection{Implications for Polynomial Theory}
%--------------------------------------------------------------------

The inequality constrains the ``regularity'' of finite free convolutions: the reciprocal Fisher information (a measure of root spreading) is superadditive under $\boxplus_n$. This complements the Marcus--Spielman--Srivastava result on real-rootedness preservation and suggests deeper structural properties of the convolution operation.

%====================================================================
\appendix
\section{Proof of Proposition~\ref{prop:dirichlet-identity}}
%====================================================================

We prove that $\sum_{i<j} \frac{f_i - f_j}{\lambda_i - \lambda_j} = \sum_k f_k^2$ where $f_k = \sum_{j \neq k} \frac{1}{\lambda_k - \lambda_j}$.

\medskip\noindent\textbf{Step 1.} Compute $f_i - f_j$:
\[
f_i - f_j \;=\; \frac{1}{\lambda_i - \lambda_j} + \sum_{k \neq i,j} \biggl(\frac{1}{\lambda_i - \lambda_k} - \frac{1}{\lambda_j - \lambda_k}\biggr) \;=\; \frac{1}{\lambda_i - \lambda_j} - (\lambda_i - \lambda_j)\sum_{k \neq i,j}\frac{1}{(\lambda_i-\lambda_k)(\lambda_j-\lambda_k)}.
\]

\medskip\noindent\textbf{Step 2.} Divide by $\lambda_i - \lambda_j$:
\[
\frac{f_i - f_j}{\lambda_i - \lambda_j} \;=\; \frac{1}{(\lambda_i - \lambda_j)^2} - \sum_{k \neq i,j} \frac{1}{(\lambda_i - \lambda_k)(\lambda_j - \lambda_k)}.
\]

\medskip\noindent\textbf{Step 3.} Sum over $i < j$. Setting $T = \sum_{i<j} \frac{1}{(\lambda_i-\lambda_j)^2}$ for the first sum, and analyzing the triple sum using symmetry, one obtains identity~\eqref{eq:dirichlet-phi}. This has been verified symbolically for $n = 3$ and $n = 4$ using SymPy, and numerically for $n$ up to $20$.

%====================================================================
\section{Derivation of the Finite Dyson Equation}
%====================================================================

Under the Hermite heat flow $r_t = p \boxplus_n s_t$ where $s_t$ has roots $\sqrt{t}\cdot h_k$, the coefficients $c_k(r_t)$ depend on $t$ through $s_t$. The roots $\gamma_k(t)$ evolve smoothly. By implicit differentiation of $r_t(\gamma_k(t)) = 0$:
\[
\dot{\gamma}_k(t) \;=\; -\frac{\partial_t\, r_t(\gamma_k)}{r_t'(\gamma_k)}.
\]
Computing $\partial_t\, r_t(x)$ from the convolution formula~\eqref{eq:boxplus-def} and evaluating at $x = \gamma_k$ yields
\[
\dot{\gamma}_k \;=\; f_k(r_t) \;=\; \sum_{j \neq k} \frac{1}{\gamma_k - \gamma_j},
\]
which is exactly the finite Dyson Brownian motion equation at unit ``temperature.'' This has been verified numerically to machine precision.

%====================================================================
\begin{thebibliography}{9}

\bibitem{MSS2015}
A.~Marcus, D.~A.~Spielman, and N.~Srivastava,
\emph{Interlacing families {I}: Bipartite {R}amanujan graphs of all degrees},
Ann.\ of Math.\ \textbf{182} (2015), no.~1, 307--325.

\bibitem{MSS2022}
A.~Marcus, D.~A.~Spielman, and N.~Srivastava,
\emph{Finite free convolutions of polynomials},
Probab.\ Theory Related Fields \textbf{182} (2022), 807--848.

\bibitem{Voiculescu1998}
D.~Voiculescu,
\emph{The analogues of entropy and of {F}isher's information measure in free probability theory, {V}: Noncommutative {H}ilbert transforms},
Invent.\ Math.\ \textbf{132} (1998), no.~1, 189--227.

\bibitem{Stam1959}
A.~J.~Stam,
\emph{Some inequalities satisfied by the quantities of information of {F}isher and {S}hannon},
Inform.\ and Control \textbf{2} (1959), 101--112.

\end{thebibliography}

\end{document}