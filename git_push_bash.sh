#!/bin/bash

# chmod +x git_push.sh
# ./git_push.sh "기능 추가: 로그인 페이지 구현"
commit_message="$1"

# 커밋 메시지가 비어있는지 확인
if [ -z "$commit_message" ]; then
  echo "커밋 메시지를 입력해주세요."
  echo "사용법: ./git_commit.sh \"커밋 메시지\""
  exit 1
fi

git add .
git commit -m "$commit_message"
git push origin main

echo "-----------------------------------"
echo "Git 자동화 완료!"
echo "커밋 메시지: $commit_message"
echo "-----------------------------------"
