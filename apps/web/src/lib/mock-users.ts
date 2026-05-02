export type SessionUser = {
  learner_id: string;
  org_id: string | null;
  role: string;
  name: string;
};

export type MockUser = SessionUser & {
  id: string;
  label: string;
};

export const MOCK_USERS: MockUser[] = [
  {
    id: "learner_A",
    learner_id: "learner_A",
    org_id: null,
    role: "learner",
    name: "学習者 A",
    label: "学習者 A（learner_A）",
  },
  {
    id: "learner_B",
    learner_id: "learner_B",
    org_id: null,
    role: "learner",
    name: "学習者 B",
    label: "学習者 B（learner_B）",
  },
  {
    id: "learner_C",
    learner_id: "learner_C",
    org_id: null,
    role: "learner",
    name: "学習者 C",
    label: "学習者 C（learner_C）",
  },
  {
    id: "learner_demo_001",
    learner_id: "learner_demo_001",
    org_id: null,
    role: "learner",
    name: "田中 太郎",
    label: "学習者 A（田中 太郎）",
  },
  {
    id: "learner_demo_300",
    learner_id: "learner_demo_300",
    org_id: null,
    role: "learner",
    name: "佐藤 花子",
    label: "学習者 B（佐藤 花子）",
  },
  {
    id: "learner_demo_1000",
    learner_id: "learner_demo_1000",
    org_id: null,
    role: "learner",
    name: "鈴木 一郎",
    label: "学習者 C（鈴木 一郎）",
  },
  {
    id: "supervisor_demo",
    learner_id: "supervisor_demo",
    org_id: "local",
    role: "supervisor",
    name: "山田 監督",
    label: "監督者（山田 監督）",
  },
  {
    id: "org_admin_demo",
    learner_id: "org_admin_demo",
    org_id: "local",
    role: "organization_admin",
    name: "管理部 中村",
    label: "組織管理者（管理部 中村）",
  },
  {
    id: "content_admin_demo",
    learner_id: "content_admin_demo",
    org_id: null,
    role: "content_admin",
    name: "教材開発 林",
    label: "コンテンツ管理者（教材開発 林）",
  },
  {
    id: "platform_admin_demo",
    learner_id: "platform_admin_demo",
    org_id: null,
    role: "platform_admin",
    name: "システム管理 伊藤",
    label: "プラットフォーム管理者（システム管理 伊藤）",
  },
];
