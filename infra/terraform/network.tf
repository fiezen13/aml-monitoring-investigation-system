// Mạng riêng cho hạ tầng CI. Không dùng VPC mặc định của tài khoản: VPC mặc
// định có sẵn ở mọi vùng với cấu hình mà không ai trong nhóm chọn, và nó dùng
// chung với mọi thứ khác trong tài khoản. Tự dựng thì xoá sạch được bằng một
// lệnh destroy, và biết chắc trong đó có gì.

resource "aws_vpc" "main" {
  cidr_block           = "10.20.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "${var.project}-vpc"
  }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "${var.project}-igw"
  }
}

// Một subnet công khai là đủ. Kiến trúc thật sẽ tách subnet riêng tư cho cơ
// sở dữ liệu, nhưng ở đây PostgreSQL chạy trong container trên chính máy này
// và không mở cổng ra ngoài (xem deploy/docker-compose.staging.yml), nên
// thêm tầng mạng nữa chỉ làm phức tạp mà không giảm rủi ro nào.
resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.20.1.0/24"
  availability_zone       = data.aws_availability_zones.available.names[0]
  map_public_ip_on_launch = false

  tags = {
    Name = "${var.project}-public"
  }
}

data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = {
    Name = "${var.project}-public-rt"
  }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}
