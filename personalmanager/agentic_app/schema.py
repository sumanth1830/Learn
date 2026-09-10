import operator
from enum import Enum
from pydantic import BaseModel, Field
from typing import Annotated, List, Optional, TypedDict, Literal


class QuizDetails(BaseModel):
    """
    A plain, typed snapshot of the fields the graph actually needs from the
    Django Quiz model - built once in tasks.py, before the graph starts.
    The graph never touches the live Django model itself, only this.
    """
    quiz_topic: str
    exam_name: str
    difficulty: Literal["EASY", "MED", "HARD"]
    description: str = ""
    tips_for_quiz_creation: str = ""
    max_questions: int = Field(ge=1, le=20)


class QuestionTypeEnums(str, Enum):
    SQ = "single choice question"
    MCQ = "multiple choice question"


class QuizItem(BaseModel):
    question: Annotated[str, Field(description="Question text")]
    options: Annotated[
        List[str],
        Field(description="Exactly 4 answer option strings.", min_length=4, max_length=4),
    ]
    answer: Annotated[
        Literal["A", "B", "C", "D"],
        Field(description="The letter corresponding to the correct option in `options` (A=1st, B=2nd, C=3rd, D=4th).")
    ]
    hint: Annotated[str, Field(description="A helpful suggestion or a clue which helps to figure out the answer.")]
    explanation: Annotated[
        str,
        Field(description=(
            "1-3 sentences explaining why the correct answer is correct, "
            "citing the reasoning or facts from the source document. Must "
            "be grounded strictly in the provided source material — do not "
            "explain using outside knowledge."
        ))
    ]
    question_type: Annotated[
        Literal[QuestionTypeEnums.SQ],
        Field(description="Type of question: single choice")
    ]
    source_citation: Annotated[str, Field(description="Source text that's used to frame the question, answer options.")]


class Quiz(BaseModel):
    quiz_items: Annotated[List[QuizItem], Field(description="List of quiz items")]


class FeedbackItem(BaseModel):
    indices: List[int]
    note: str

class QuizEvaluation(BaseModel):
    status: Annotated[Literal["APPROVED", "REJECTED"], Field(description="Status of the Evaluation")]
    feedback_items: List[FeedbackItem]


class GuardrailCheck(BaseModel):
    passed: bool
    reason: str
    category: Literal[
        "passed", "profanity", "injection", "off_topic",
        "manipulative", "inappropriate_source"
    ]

class CorrectedQuestion(BaseModel):
    index: int
    corrected_item: QuizItem

class CorrectionOutput(BaseModel):
    corrections: List[CorrectedQuestion]


class SafetyCheck(BaseModel):
    passed: bool
    reason: str
    category: Literal["passed", "gratuitous_detail", "tone_mismatch"]


class State(TypedDict):
    quiz_details: QuizDetails
    source_text: str
    guardrail_passed: bool
    guardrail_reason: str
    generated_quiz: Optional[Quiz]
    structural_check_passed: bool
    safety_passed: bool
    safety_reason: str
    evaluation_status: Literal["APPROVED", "REJECTED"]
    retry_reason: Literal["structural", "evaluation"]
    retry_feedback: str
    evaluation_feedback_items: List[FeedbackItem]
    structural_attempts: Annotated[int, operator.add]
    evaluator_attempts: Annotated[int, operator.add]
    guardrail_category: str
    safety_category: str
    end_reason: Optional[str]