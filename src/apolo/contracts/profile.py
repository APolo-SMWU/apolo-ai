"""사용자 직접 입력을 Seed로 변환하기 위한 입력 계약"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

UserType = Literal["student", "professor", "professional"]


class MyPageProfile(BaseModel):

    model_config = ConfigDict(extra="forbid", strict=True)

    name: str
    email: str
    phone: str | None = None
    github: str | None = None
    company: str | None = None
    job_title: str | None = Field(default=None, alias="jobTitle")
    tel: str | None = None
    university: str | None = None
    department: str | None = None
    major: str | None = None


class SeedProfileInput(BaseModel):

    model_config = ConfigDict(extra="forbid", strict=True)

    user_id: int = Field(gt=0, alias="userId")
    user_type: UserType = Field(alias="userType")
    my_page_profile: MyPageProfile = Field(alias="myPageProfile")
